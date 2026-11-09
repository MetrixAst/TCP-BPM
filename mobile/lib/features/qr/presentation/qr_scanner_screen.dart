import 'dart:async';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../../core/camera/camera_access.dart';
import '../../../shared/spacing.dart';

enum _Phase { checkingAccess, noAccess, starting, running, failed }

class QrScannerScreen extends StatefulWidget {
  const QrScannerScreen({super.key});

  @override
  State<QrScannerScreen> createState() => _QrScannerScreenState();
}

class _QrScannerScreenState extends State<QrScannerScreen> with WidgetsBindingObserver {
  // Камера на части устройств не стартует или зависает без ответа, поэтому
  // старт ограничен по времени, а у планшетов без задней камеры есть
  // запасной вариант — фронтальная.
  static const _startTimeout = Duration(seconds: 10);
  static const _facings = [CameraFacing.back, CameraFacing.front];

  final MobileScannerController _controller = MobileScannerController(
    autoStart: false,
    detectionSpeed: DetectionSpeed.noDuplicates,
    formats: const [BarcodeFormat.qrCode],
  );

  _Phase _phase = _Phase.checkingAccess;
  bool _accessPermanentlyDenied = false;
  bool _hasScanned = false;
  bool _busy = false;
  bool _analyzingPhoto = false;
  String? _errorCode;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _prepare());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_controller.dispose());
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        // Вернулись из настроек телефона или из другого приложения.
        if (_phase == _Phase.noAccess) {
          unawaited(_recheckAccess());
        } else if (_phase == _Phase.running) {
          unawaited(_startCamera());
        }
      case AppLifecycleState.inactive:
      case AppLifecycleState.paused:
        if (_phase == _Phase.running) unawaited(_controller.stop());
      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
        break;
    }
  }

  void _setPhase(_Phase phase) {
    if (mounted) setState(() => _phase = phase);
  }

  Future<void> _prepare() async {
    if (_busy || _hasScanned || !mounted) return;
    _busy = true;
    _setPhase(_Phase.checkingAccess);
    final access = await requestCameraAccess();
    _busy = false;
    if (!mounted) return;
    if (access != CameraAccess.granted) {
      setState(() {
        _accessPermanentlyDenied = access == CameraAccess.permanentlyDenied;
        _phase = _Phase.noAccess;
      });
      return;
    }
    await _startCamera();
  }

  Future<void> _recheckAccess() async {
    if (await hasCameraAccess()) await _startCamera();
  }

  /// Сбрасывает нативную сессию камеры, которая осталась от прошлого открытия
  /// сканера. Если экран закрыли, пока камера запускалась, плагин всё равно
  /// дозапускает её, и следующий start() отвечает controllerAlreadyInitialized,
  /// а контроллер так и не получает картинку — пользователь видит чёрный экран.
  Future<void> _releaseStaleSession() async {
    if (_controller.value.isRunning) return;
    try {
      await MobileScannerPlatform.instance.stop();
    } catch (_) {
      // Сессии не было — сбрасывать нечего.
    }
  }

  /// Запускает камеру. Если запуск не уложился в [_startTimeout], ждём его
  /// ещё столько же: брошенный старт плагин всё равно доведёт до конца
  /// и займёт камеру.
  Future<void> _start(CameraFacing facing) async {
    final pending = _controller.start(cameraDirection: facing);
    try {
      await pending.timeout(_startTimeout);
    } on TimeoutException {
      await pending.timeout(_startTimeout, onTimeout: () {});
      if (!_controller.value.isRunning) rethrow;
    }
  }

  Future<void> _startCamera() async {
    if (_busy || _hasScanned || !mounted) return;
    _busy = true;
    setState(() {
      _phase = _Phase.starting;
      _errorCode = null;
    });
    // Виджет MobileScanner должен появиться до start(): в debug-сборке он при
    // монтировании принудительно останавливает камеру.
    await WidgetsBinding.instance.endOfFrame;
    if (!mounted) return;

    String? lastCode;
    var started = false;
    outer:
    for (final facing in _facings) {
      for (var attempt = 0; attempt < 2; attempt++) {
        try {
          await _releaseStaleSession();
          await _start(facing);
          // start() не выбрасывает ошибку запуска, а кладёт её в value.error.
          final state = _controller.value;
          if (state.isRunning) {
            started = true;
            break outer;
          }
          throw state.error ?? const MobileScannerException(errorCode: MobileScannerErrorCode.genericError);
        } on MobileScannerException catch (e) {
          lastCode = e.errorDetails?.code ?? e.errorCode.name;
          if (e.errorCode == MobileScannerErrorCode.permissionDenied) {
            _busy = false;
            setState(() => _phase = _Phase.noAccess);
            return;
          }
          if (e.errorCode == MobileScannerErrorCode.unsupported) break;
        } on TimeoutException {
          lastCode = 'timeout';
        } catch (e) {
          lastCode = e.runtimeType.toString();
        }
        await _controller.stop().catchError((_) {});
        await _releaseStaleSession();
        await Future<void>.delayed(Duration(milliseconds: 700 * (attempt + 1)));
        if (!mounted) return;
      }
    }

    _busy = false;
    if (!mounted) return;
    setState(() {
      _phase = started ? _Phase.running : _Phase.failed;
      _errorCode = started ? null : lastCode;
    });
  }

  Future<void> _requestAccessAgain() async {
    if (_accessPermanentlyDenied) {
      await openCameraSettings();
      return;
    }
    await _prepare();
  }

  void _finish(String rawValue) {
    if (_hasScanned || !mounted) return;
    setState(() => _hasScanned = true);
    unawaited(_controller.stop());
    Navigator.of(context).pop(rawValue);
  }

  void _handleDetect(BarcodeCapture capture) {
    if (_hasScanned) return;
    for (final barcode in capture.barcodes) {
      final rawValue = barcode.rawValue;
      if (rawValue != null && rawValue.isNotEmpty) {
        _finish(rawValue);
        return;
      }
    }
  }

  /// Запасной путь для устройств, где живая камера не работает: QR снимается
  /// системным приложением камеры (или берётся из галереи) и распознаётся
  /// по фото.
  Future<void> _scanFromPhoto(ImageSource source) async {
    if (_analyzingPhoto) return;
    if (source == ImageSource.camera && !await ensureCameraAccess(context)) return;

    if (_phase == _Phase.running) await _controller.stop();
    setState(() => _analyzingPhoto = true);
    String? message;
    try {
      final file = await ImagePicker().pickImage(source: source, maxWidth: 2000, maxHeight: 2000);
      if (file == null) return;
      final capture = await _controller.analyzeImage(file.path, formats: const [BarcodeFormat.qrCode]);
      final rawValue = capture?.barcodes
          .map((b) => b.rawValue)
          .firstWhere((v) => v != null && v.isNotEmpty, orElse: () => null);
      if (rawValue != null) {
        _finish(rawValue);
        return;
      }
      message = 'QR-код на фото не найден. Снимите код ближе и ровнее, чтобы он занимал большую часть кадра.';
    } catch (_) {
      message = 'Не удалось распознать фото. Попробуйте ещё раз.';
    } finally {
      if (mounted) setState(() => _analyzingPhoto = false);
      if (mounted && !_hasScanned && _phase == _Phase.running && !_controller.value.isRunning) {
        unawaited(_startCamera());
      }
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  void _toggleTorch() {
    if (!_controller.value.isRunning) return;
    unawaited(_controller.toggleTorch().catchError((_) {}));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('Сканировать QR'),
        actions: [if (_phase == _Phase.running) IconButton(icon: const Icon(Icons.flash_on), onPressed: _toggleTorch)],
      ),
      body: Stack(
        children: [
          Positioned.fill(child: _buildBody()),
          if (_analyzingPhoto)
            const Positioned.fill(
              child: ColoredBox(
                color: Colors.black54,
                child: Center(child: CircularProgressIndicator(color: Colors.white)),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildBody() {
    switch (_phase) {
      case _Phase.checkingAccess:
        return const Center(child: CircularProgressIndicator(color: Colors.white));
      case _Phase.noAccess:
        return _ScannerMessage(
          icon: Icons.no_photography_outlined,
          message: _accessPermanentlyDenied
              ? 'Доступ к камере для metriX запрещён. Откройте настройки приложения, включите «Камера» и вернитесь сюда.'
              : cameraDeniedMessage,
          primaryLabel: _accessPermanentlyDenied ? 'Открыть настройки' : 'Разрешить доступ',
          onPrimary: _requestAccessAgain,
          onGallery: () => _scanFromPhoto(ImageSource.gallery),
        );
      case _Phase.failed:
        return _ScannerMessage(
          icon: Icons.videocam_off_outlined,
          message: 'Камера не запустилась. Сфотографируйте QR-код — он распознается по фото.',
          code: _errorCode,
          primaryLabel: 'Сфотографировать QR',
          onPrimary: () => _scanFromPhoto(ImageSource.camera),
          secondaryLabel: 'Повторить',
          onSecondary: _startCamera,
          onGallery: () => _scanFromPhoto(ImageSource.gallery),
        );
      case _Phase.starting:
      case _Phase.running:
        // Пока камера запускается, сканер уже в дереве (см. _startCamera),
        // а поверх него — индикатор загрузки.
        return Stack(
          children: [
            Positioned.fill(
              child: MobileScanner(
                controller: _controller,
                onDetect: _handleDetect,
                errorBuilder: (context, error, child) => _ScannerMessage(
                  icon: Icons.videocam_off_outlined,
                  message: 'Камера не запустилась. Сфотографируйте QR-код — он распознается по фото.',
                  code: error.errorDetails?.code ?? error.errorCode.name,
                  primaryLabel: 'Сфотографировать QR',
                  onPrimary: () => _scanFromPhoto(ImageSource.camera),
                  secondaryLabel: 'Повторить',
                  onSecondary: _startCamera,
                  onGallery: () => _scanFromPhoto(ImageSource.gallery),
                ),
              ),
            ),
            if (_phase == _Phase.starting)
              const Positioned.fill(
                child: ColoredBox(
                  color: Colors.black,
                  child: Center(child: CircularProgressIndicator(color: Colors.white)),
                ),
              ),
            if (_phase == _Phase.running) ...[
              Center(
                child: Container(
                  width: 240,
                  height: 240,
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.white, width: 2),
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
              ),
              Positioned(
                bottom: 32,
                left: 0,
                right: 0,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text(
                        'Наведите камеру на QR-код',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: Colors.white, fontSize: 14),
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      TextButton.icon(
                        onPressed: () => _scanFromPhoto(ImageSource.camera),
                        icon: const Icon(Icons.photo_camera_outlined, color: Colors.white70),
                        label: const Text('Не сканирует? Сфотографировать QR', style: TextStyle(color: Colors.white70)),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        );
    }
  }
}

class _ScannerMessage extends StatelessWidget {
  const _ScannerMessage({
    required this.icon,
    required this.message,
    required this.primaryLabel,
    required this.onPrimary,
    required this.onGallery,
    this.code,
    this.secondaryLabel,
    this.onSecondary,
  });

  final IconData icon;
  final String message;
  final String? code;
  final String primaryLabel;
  final VoidCallback onPrimary;
  final String? secondaryLabel;
  final VoidCallback? onSecondary;
  final VoidCallback onGallery;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, color: Colors.white70, size: 48),
              const SizedBox(height: AppSpacing.md),
              Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white, fontSize: 15),
              ),
              if (code != null) ...[
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Код: $code',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white38, fontSize: 12),
                ),
              ],
              const SizedBox(height: AppSpacing.lg),
              SizedBox(
                width: double.infinity,
                child: FilledButton(onPressed: onPrimary, child: Text(primaryLabel)),
              ),
              if (secondaryLabel != null && onSecondary != null) ...[
                const SizedBox(height: AppSpacing.sm),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: onSecondary,
                    style: OutlinedButton.styleFrom(foregroundColor: Colors.white),
                    child: Text(secondaryLabel!),
                  ),
                ),
              ],
              const SizedBox(height: AppSpacing.sm),
              TextButton(
                onPressed: onGallery,
                child: const Text('Выбрать фото QR из галереи', style: TextStyle(color: Colors.white70)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
