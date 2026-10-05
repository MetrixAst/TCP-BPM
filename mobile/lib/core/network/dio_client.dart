import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'auth_interceptor.dart';

class DioClient {
  late final Dio dio;

  DioClient() {
    final baseUrl = const String.fromEnvironment(
      'BASE_URL',
      defaultValue: 'https://api.metrix.example.com',
    );
    dio = Dio(
      BaseOptions(
        baseUrl: baseUrl,
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 10),
        headers: {
          // ngrok free interstitial blocks XHR without this header
          if (baseUrl.contains('ngrok')) 'ngrok-skip-browser-warning': '1',
        },
      ),
    );

    dio.interceptors.add(
      AuthInterceptor(dio: dio, storage: const FlutterSecureStorage()),
    );
    dio.interceptors.add(
      LogInterceptor(requestBody: true, responseBody: true),
    );
  }
}