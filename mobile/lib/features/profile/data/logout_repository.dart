import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class LogoutRepository {
  final Dio dio;
  final FlutterSecureStorage storage;

  static const _accessKey = 'auth_access_token';
  static const _refreshKey = 'auth_refresh_token';

  LogoutRepository({required this.dio, required this.storage});

  Future<void> logout() async {
    try {
      await dio.delete('/api/v1/mobile/devices/');
    } catch (_) {
      // Не блокируем логаут, даже если отвязка устройства не удалась
      // (например, нет сети) — главное всё равно выйти локально.
    }

    await storage.delete(key: _accessKey);
    await storage.delete(key: _refreshKey);
  }
}