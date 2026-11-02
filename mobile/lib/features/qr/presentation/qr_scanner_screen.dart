import 'dart:async';

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../../shared/spacing.dart';

class QrScannerScreen extends StatefulWidget {
  const QrScannerScreen({super.key});

  @override
  State<QrScannerScreen> createState() => _QrScannerScreenState();
}

class _QrScannerScreenState extends State<QrScannerScreen> with WidgetsBindingObserver {
  final MobileScannerController _controller = MobileScannerController(
    autoStart: false,
    detectionSpeed: DetectionSpeed.noDuplicates,
    formats: const [BarcodeFormat.qrCode],
  );
  bool _hasScanned = false;
  bool _starting = false;
  MobileScannerException? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _start());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_controller.dispose());
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!_controller.value.hasCameraPermission) return;
    switch (state) {
      case AppLifecycleState.resumed:
        _start();
      case AppLifecycleState.inactive:
      case AppLifecycleState.paused:
        unawaited(_controller.stop());
      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
        break;
    }
  }

  /// Android отклоняет запрос камеры, пока открыт другой системный диалог
  /// (уведомления, геолокация), и только что закрытая камера освобождается
  /// не сразу. Поэтому старт повторяется несколько раз с паузой.
  Future<void> _start() async {
    if (_starting || _hasScanned || !mounted) return;
    _starting = true;
    setState(() => _error = null);

    MobileScannerException? lastError;
    for (var attempt = 0; attempt < 3; attempt++) {
      try {
        await _controller.start();
        lastError = null;
        break;
      } on MobileScannerException catch (e) {
        lastError = e;
        if (e.errorCode == MobileScannerErrorCode.controllerAlreadyInitialized) {
          lastError = null;
          break;
        }
        if (e.errorCode == MobileScannerErrorCode.permissionDenied ||
            e.errorCode == MobileScannerErrorCode.unsupported) {
          break;
        }
        await _controller.stop();
        await Future<void>.delayed(Duration(milliseconds: 600 * (attempt + 1)));
        if (!mounted) break;
      }
    }

    _starting = false;
    if (mounted) setState(() => _error = lastError);
  }

  void _handleDetect(BarcodeCapture capture) {
    if (_hasScanned) return;

    final barcodes = capture.barcodes;
    if (barcodes.isEmpty) return;

    final rawValue = barcodes.first.rawValue;
    if (rawValue == null || rawValue.isEmpty) return;

    setState(() => _hasScanned = true);
    unawaited(_controller.stop());
    Navigator.of(context).pop(rawValue);
  }

  void _toggleTorch() {
    if (!_controller.value.isRunning) return;
    unawaited(_controller.toggleTorch());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('Сканировать QR'),
        actions: [
          IconButton(
            icon: const Icon(Icons.flash_on),
            onPressed: _toggleTorch,
          ),
        ],
      ),
      body: _error != null
          ? _ScannerError(error: _error!, onRetry: _start)
          : Stack(
              children: [
                MobileScanner(
                  controller: _controller,
                  onDetect: _handleDetect,
                  errorBuilder: (context, error, child) => _ScannerError(error: error, onRetry: _start),
                ),
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
                  bottom: 60,
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
            ),
    );
  }
}

class _ScannerError extends StatelessWidget {
  const _ScannerError({required this.error, required this.onRetry});

  final MobileScannerException error;
  final VoidCallback onRetry;

  bool get _denied => error.errorCode == MobileScannerErrorCode.permissionDenied;

  String get _message {
    switch (error.errorCode) {
      case MobileScannerErrorCode.permissionDenied:
        return 'Нет доступа к камере. Разрешите камеру для metriX в настройках телефона.';
      case MobileScannerErrorCode.unsupported:
        return 'На этом устройстве не найдена камера для сканирования.';
      default:
        return 'Не удалось запустить камеру. Закройте другие приложения, которые используют камеру, и нажмите «Повторить».';
    }
  }

  @override
  Widget build(BuildContext context) {
    final code = error.errorDetails?.code ?? error.errorCode.name;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.no_photography_outlined, color: Colors.white70, size: 48),
            const SizedBox(height: AppSpacing.md),
            Text(
              _message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white, fontSize: 15),
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              'Код: $code',
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white38, fontSize: 12),
            ),
            const SizedBox(height: AppSpacing.lg),
            FilledButton(
              onPressed: _denied ? Geolocator.openAppSettings : onRetry,
              child: Text(_denied ? 'Открыть настройки' : 'Повторить'),
            ),
          ],
        ),
      ),
    );
  }
}
