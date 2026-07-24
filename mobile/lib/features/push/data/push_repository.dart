import 'package:dio/dio.dart';

class PushRepository {
  final Dio dio;

  PushRepository({required this.dio});

  Future<void> registerToken(String fcmToken) async {
    await dio.post('/api/v1/mobile/devices/', data: {'fcm': fcmToken});
  }

  Future<void> unregisterToken(String fcmToken) async {
    await dio.delete('/api/v1/mobile/devices/', data: {'fcm': fcmToken});
  }
}