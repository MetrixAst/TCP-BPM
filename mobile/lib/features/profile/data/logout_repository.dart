import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../../push/data/push_service.dart';

class LogoutRepository {
  final Dio dio;
  final FlutterSecureStorage storage;
  final PushService? pushService;

  static const _accessKey = 'auth_access_token';
  static const _refreshKey = 'auth_refresh_token';

  LogoutRepository({
    required this.dio,
    required this.storage,
    this.pushService,
  });

  Future<void> logout() async {
    try {
      final fcmToken = await (pushService ?? PushService()).getToken();
      if (fcmToken != null) {
        await dio.delete('/api/v1/mobile/devices/', data: {'fcm': fcmToken});
      } else {
        await dio.delete('/api/v1/mobile/devices/');
      }
    } catch (_) {
      // Не блокируем логаут, даже если отвязка устройства не удалась
    }

    await storage.delete(key: _accessKey);
    await storage.delete(key: _refreshKey);
  }
}