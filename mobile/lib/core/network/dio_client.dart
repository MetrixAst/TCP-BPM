import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'auth_interceptor.dart';
import 'server_config.dart';

class DioClient {
  late final Dio dio;

  DioClient() {
    dio = Dio(
      BaseOptions(
        baseUrl: ServerConfig.baseUrl,
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 10),
      ),
    );

    // Сервер может смениться после входа через шлюз — клиенты, созданные
    // раньше, подхватывают актуальный адрес перед каждым запросом.
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          options.baseUrl = ServerConfig.baseUrl;
          handler.next(options);
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