import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthInterceptor extends Interceptor {
  final Dio dio;
  final FlutterSecureStorage storage;
  final Dio? refreshDio; // позволяет подменить в тестах

  static const _accessKey = 'auth_access_token';
  static const _refreshKey = 'auth_refresh_token';

  bool _isRefreshing = false;

  AuthInterceptor({
    required this.dio,
    required this.storage,
    this.refreshDio,
  });

  Dio get _refreshClient =>
      refreshDio ?? Dio(BaseOptions(baseUrl: dio.options.baseUrl));

  @override
  Future<void> onRequest(
      RequestOptions options,
      RequestInterceptorHandler handler,
      ) async {
    options.headers['User-Agent'] = 'flutter_app';

    final token = await storage.read(key: _accessKey);
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }

    handler.next(options);
  }

  @override
  Future<void> onError(
      DioException err,
      ErrorInterceptorHandler handler,
      ) async {
    if (err.response?.statusCode != 401 || _isRefreshing) {
      return handler.next(err);
    }

    final refreshToken = await storage.read(key: _refreshKey);
    if (refreshToken == null) {
      await _globalLogout();
      return handler.next(err);
    }

    _isRefreshing = true;
    try {
      final response = await _refreshClient.post(
        '/api/token/refresh/',
        data: {'refresh': refreshToken},
      );

      final newAccess = response.data['access'] as String;
      await storage.write(key: _accessKey, value: newAccess);

      final retryOptions = err.requestOptions;
      retryOptions.headers['Authorization'] = 'Bearer $newAccess';

      final retryResponse = await dio.fetch(retryOptions);
      _isRefreshing = false;
      return handler.resolve(retryResponse);
    } catch (_) {
      _isRefreshing = false;
      await _globalLogout();
      return handler.next(err);
    }
  }

  Future<void> _globalLogout() async {
    await storage.delete(key: _accessKey);
    await storage.delete(key: _refreshKey);
  }
}