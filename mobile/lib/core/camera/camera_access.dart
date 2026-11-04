import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

enum CameraAccess { granted, denied, permanentlyDenied }

/// Разрешение на камеру запрашивается здесь, а не внутри плагинов камеры:
/// mobile_scanner на части Android-устройств отдаёт вместо отказа
/// «An unexpected error occurred», а image_picker — исключение.
Future<CameraAccess> requestCameraAccess() async {
  var status = await Permission.camera.status;
  if (status.isGranted || status.isLimited) return CameraAccess.granted;
  if (status.isPermanentlyDenied || status.isRestricted) {
    return CameraAccess.permanentlyDenied;
  }

  status = await Permission.camera.request();
  if (status.isGranted || status.isLimited) return CameraAccess.granted;
  if (status.isPermanentlyDenied || status.isRestricted) {
    return CameraAccess.permanentlyDenied;
  }
  return CameraAccess.denied;
}

Future<bool> hasCameraAccess() async {
  final status = await Permission.camera.status;
  return status.isGranted || status.isLimited;
}

Future<void> openCameraSettings() => openAppSettings();

const cameraDeniedMessage =
    'Нет доступа к камере. Разрешите доступ к камере для metriX, иначе фото и QR-коды не работают.';

/// Проверяет доступ к камере и, если его нет, объясняет это пользователю.
/// Возвращает true, только когда камерой можно пользоваться.
Future<bool> ensureCameraAccess(BuildContext context) async {
  final access = await requestCameraAccess();
  if (access == CameraAccess.granted) return true;
  if (!context.mounted) return false;

  final permanently = access == CameraAccess.permanentlyDenied;
  final openSettings = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Нет доступа к камере'),
      content: Text(
        permanently
            ? 'Доступ к камере для metriX запрещён. Откройте настройки приложения и включите «Камера».'
            : cameraDeniedMessage,
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Отмена'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(true),
          child: Text(permanently ? 'Открыть настройки' : 'Разрешить'),
        ),
      ],
    ),
  );

  if (openSettings != true) return false;
  if (permanently) {
    await openCameraSettings();
    return false;
  }
  return await requestCameraAccess() == CameraAccess.granted;
}
