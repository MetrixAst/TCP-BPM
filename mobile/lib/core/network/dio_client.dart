import 'package:dio/dio.dart';

class DioClient {
  late final Dio dio;

  DioClient() {
    dio = Dio(
      BaseOptions(
        baseUrl: const String.fromEnvironment(
          'BASE_URL',
          defaultValue: 'https://api.metrix.example.com',
        ),
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 10),
      ),
    );

    dio.interceptors.add(
      LogInterceptor(requestBody: true, responseBody: true),
    );
  }
}