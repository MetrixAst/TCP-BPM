import 'dart:async';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../../core/camera/camera_access.dart';
import '../../../shared/spacing.dart';

enum _Phase { checkingAccess, noAccess, starting, running, failed }

const _cameraFailedMessage =
    'Камера не запустилась. Закройте другие приложения, которые используют камеру, и нажмите «Повторить».';

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
      body: _buildBody(),
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
        );
      case _Phase.failed:
        return _ScannerMessage(
          icon: Icons.videocam_off_outlined,
          message: _cameraFailedMessage,
          code: _errorCode,
          primaryLabel: 'Повторить',
          onPrimary: _startCamera,
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
                  message: _cameraFailedMessage,
                  code: error.errorDetails?.code ?? error.errorCode.name,
                  primaryLabel: 'Повторить',
                  onPrimary: _startCamera,
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
              const Positioned(
                bottom: 32,
                left: 0,
                right: 0,
                child: Padding(
                  padding: EdgeInsets.symmetric(horizontal: AppSpacing.lg),
                  child: Text(
                    'Наведите камеру на QR-код',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white, fontSize: 14),
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
    this.code,
  });

  final IconData icon;
  final String message;
  final String? code;
  final String primaryLabel;
  final VoidCallback onPrimary;

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
            ],
          ),
        ),
      ),
    );
  }
}
