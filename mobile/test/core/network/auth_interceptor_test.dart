import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:metrix_app/core/network/auth_interceptor.dart';

class MockSecureStorage extends Mock implements FlutterSecureStorage {}

class MockRefreshDio extends Mock implements Dio {}

/// Имитирует сеть: /protected отвечает 401 на первый вызов
/// и 200 на повторный (после refresh) — так проверяем retry.
class FakeAdapter implements HttpClientAdapter {
  int callCount = 0;

  @override
  Future<ResponseBody> fetch(
      RequestOptions options,
      Stream<Uint8List>? requestStream,
      Future<void>? cancelFuture,
      ) async {
    if (options.path == '/protected') {
      callCount++;
      if (callCount == 1) {
        return ResponseBody.fromString(
          '{"detail":"Unauthorized"}',
          401,
          headers: {
            Headers.contentTypeHeader: [Headers.jsonContentType],
          },
        );
      }
      return ResponseBody.fromString(
        '{"ok":true}',
        200,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );
    }
    throw Exception('Unexpected path in test: ${options.path}');
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  late MockSecureStorage storage;
  late MockRefreshDio refreshDio;
  late Dio dio;
  late AuthInterceptor authInterceptor;

  setUp(() {
    storage = MockSecureStorage();
    refreshDio = MockRefreshDio();
    dio = Dio(BaseOptions(baseUrl: 'https://test.local'))
      ..httpClientAdapter = FakeAdapter();
    authInterceptor = AuthInterceptor(dio: dio, storage: storage, refreshDio: refreshDio);
    dio.interceptors.add(authInterceptor);
  });

  test('onRequest добавляет Bearer токен и User-Agent', () async {
    when(() => storage.read(key: 'auth_access_token'))
        .thenAnswer((_) async => 'myToken123');

    final options = RequestOptions(path: '/test');
    final handler = RequestInterceptorHandler();

    await authInterceptor.onRequest(options, handler); // используем прямую ссылку

    expect(options.headers['Authorization'], 'Bearer myToken123');
    expect(options.headers['User-Agent'], 'flutter_app');
  });

  test('401 -> прозрачный refresh -> повтор запроса -> успех', () async {
    when(() => storage.read(key: 'auth_access_token'))
        .thenAnswer((_) async => 'expiredToken');
    when(() => storage.read(key: 'auth_refresh_token'))
        .thenAnswer((_) async => 'validRefreshToken');
    when(() => storage.write(key: any(named: 'key'), value: any(named: 'value')))
        .thenAnswer((_) async {});
    when(() => refreshDio.post('/api/token/refresh/', data: any(named: 'data')))
        .thenAnswer(
          (_) async => Response(
        requestOptions: RequestOptions(path: '/api/token/refresh/'),
        statusCode: 200,
        data: {'access': 'newAccessToken'},
      ),
    );

    final response = await dio.get('/protected');

    expect(response.statusCode, 200);
    expect(response.data, {'ok': true});
    verify(() => refreshDio.post('/api/token/refresh/', data: any(named: 'data')))
        .called(1);
    verify(() => storage.write(key: 'auth_access_token', value: 'newAccessToken'))
        .called(1);
  });

  test('невалидный refresh -> глобальный logout, ошибка пробрасывается', () async {
    when(() => storage.read(key: 'auth_access_token'))
        .thenAnswer((_) async => 'expiredToken');
    when(() => storage.read(key: 'auth_refresh_token'))
        .thenAnswer((_) async => 'expiredRefreshToken');
    when(() => storage.delete(key: any(named: 'key'))).thenAnswer((_) async {});
    when(() => refreshDio.post('/api/token/refresh/', data: any(named: 'data')))
        .thenThrow(
      DioException(
        requestOptions: RequestOptions(path: '/api/token/refresh/'),
        response: Response(
          requestOptions: RequestOptions(path: '/api/token/refresh/'),
          statusCode: 401,
        ),
      ),
    );

    expect(
          () => dio.get('/protected'),
      throwsA(isA<DioException>()),
    );

    // ждём, пока асинхронный logout внутри onError отработает
    await Future.delayed(const Duration(milliseconds: 50));

    verify(() => storage.delete(key: 'auth_access_token')).called(1);
    verify(() => storage.delete(key: 'auth_refresh_token')).called(1);
  });

  test('нет refresh токена -> сразу logout без запроса refresh', () async {
    when(() => storage.read(key: 'auth_access_token'))
        .thenAnswer((_) async => 'expiredToken');
    when(() => storage.read(key: 'auth_refresh_token'))
        .thenAnswer((_) async => null);
    when(() => storage.delete(key: any(named: 'key'))).thenAnswer((_) async {});

    expect(
          () => dio.get('/protected'),
      throwsA(isA<DioException>()),
    );

    await Future.delayed(const Duration(milliseconds: 50));

    verifyNever(
          () => refreshDio.post('/api/token/refresh/', data: any(named: 'data')),
    );
    verify(() => storage.delete(key: 'auth_access_token')).called(1);
    verify(() => storage.delete(key: 'auth_refresh_token')).called(1);
  });
}