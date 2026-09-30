import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../../core/database/local_data_cleaner.dart';
import '../../../core/network/api_result.dart';
import 'auth_tokens.dart';

class AuthRepository {
  final Dio dio;
  final FlutterSecureStorage storage;
  final LocalDataCleaner? localDataCleaner;

  static const _accessKey = 'auth_access_token';
  static const _refreshKey = 'auth_refresh_token';
  static const _accountKey = 'auth_account';

  AuthRepository({
    required this.dio,
    required this.storage,
    this.localDataCleaner,
  });

  Future<ApiResult<AuthTokens>> login({
    required String username,
    required String password,
  }) async {
    try {
      final response = await dio.post(
        '/api/token/',
        data: {'username': username, 'password': password},
      );

      final tokens = AuthTokens.fromJson(response.data as Map<String, dynamic>);
      await _dropDataOfPreviousAccount(username);
      await _saveTokens(tokens);
      return Success(tokens);
    } on DioException catch (e) {
      return Failure(
        _errorMessage(e),
        statusCode: e.response?.statusCode,
      );
    }
  }

  Future<ApiResult<AuthTokens>> refresh() async {
    final refreshToken = await storage.read(key: _refreshKey);
    if (refreshToken == null) {
      return const Failure('Нет refresh-токена');
    }

    try {
      final response = await dio.post(
        '/api/token/refresh/',
        data: {'refresh': refreshToken},
      );

      final newAccess = response.data['access'] as String;
      final tokens = AuthTokens(access: newAccess, refresh: refreshToken);
      await _saveTokens(tokens);
      return Success(tokens);
    } on DioException catch (e) {
      // Refresh невалиден — глобальный logout
      await clear();
      return Failure(
        _errorMessage(e),
        statusCode: e.response?.statusCode,
      );
    }
  }

  /// Страховка на случай, когда предыдущий вход завершился не логаутом,
  /// а истёкшим refresh-токеном: офлайн-кэш и очередь от чужого аккаунта
  /// не должны достаться новому пользователю или другому серверу.
  Future<void> _dropDataOfPreviousAccount(String username) async {
    final account = '${dio.options.baseUrl}|$username';
    final previous = await storage.read(key: _accountKey);

    if (previous != null && previous != account) {
      try {
        await (localDataCleaner ?? LocalDataCleaner()).clear();
      } catch (_) {
        // Вход блокировать нельзя, но и молча оставлять чужой кэш тоже.
      }
    }

    await storage.write(key: _accountKey, value: account);
  }

  Future<void> _saveTokens(AuthTokens tokens) async {
    await storage.write(key: _accessKey, value: tokens.access);
    await storage.write(key: _refreshKey, value: tokens.refresh);
  }

  Future<String?> readAccessToken() => storage.read(key: _accessKey);

  Future<String?> readRefreshToken() => storage.read(key: _refreshKey);

  Future<void> clear() async {
    await storage.delete(key: _accessKey);
    await storage.delete(key: _refreshKey);
  }

  String _errorMessage(DioException e) {
    if (e.response?.statusCode == 401) {
      return 'Неверный логин или пароль';
    }
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Ошибка сети, попробуйте ещё раз';
  }
}