import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:metrix_app/features/auth/data/auth_repository.dart';
import 'package:metrix_app/features/auth/data/auth_tokens.dart';
import 'package:metrix_app/core/network/api_result.dart';

class MockDio extends Mock implements Dio {}
class MockSecureStorage extends Mock implements FlutterSecureStorage {}

void main() {
  late MockDio dio;
  late MockSecureStorage storage;
  late AuthRepository repository;

  setUp(() {
    dio = MockDio();
    storage = MockSecureStorage();
    repository = AuthRepository(dio: dio, storage: storage);
  });

  group('login', () {
    test('успешный вход сохраняет токены', () async {
      when(() => dio.post('/api/token/', data: any(named: 'data'))).thenAnswer(
            (_) async => Response(
          requestOptions: RequestOptions(path: '/api/token/'),
          statusCode: 200,
          data: {'access': 'access123', 'refresh': 'refresh123'},
        ),
      );
      when(() => storage.write(key: any(named: 'key'), value: any(named: 'value')))
          .thenAnswer((_) async {});

      final result = await repository.login(username: 'test', password: 'pass');

      expect(result, isA<Success<AuthTokens>>());
      verify(() => storage.write(key: 'auth_access_token', value: 'access123')).called(1);
      verify(() => storage.write(key: 'auth_refresh_token', value: 'refresh123')).called(1);
    });

    test('неверный пароль возвращает Failure с 401', () async {
      when(() => dio.post('/api/token/', data: any(named: 'data'))).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/token/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/token/'),
            statusCode: 401,
          ),
        ),
      );

      final result = await repository.login(username: 'test', password: 'wrong');

      expect(result, isA<Failure<AuthTokens>>());
      final failure = result as Failure<AuthTokens>;
      expect(failure.statusCode, 401);
    });
  });

  group('refresh', () {
    test('успешный refresh обновляет access token', () async {
      when(() => storage.read(key: 'auth_refresh_token'))
          .thenAnswer((_) async => 'refresh123');
      when(() => dio.post('/api/token/refresh/', data: any(named: 'data'))).thenAnswer(
            (_) async => Response(
          requestOptions: RequestOptions(path: '/api/token/refresh/'),
          statusCode: 200,
          data: {'access': 'newAccess456'},
        ),
      );
      when(() => storage.write(key: any(named: 'key'), value: any(named: 'value')))
          .thenAnswer((_) async {});

      final result = await repository.refresh();

      expect(result, isA<Success<AuthTokens>>());
    });

    test('невалидный refresh делает logout (чистит storage)', () async {
      when(() => storage.read(key: 'auth_refresh_token'))
          .thenAnswer((_) async => 'expiredRefresh');
      when(() => dio.post('/api/token/refresh/', data: any(named: 'data'))).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/token/refresh/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/token/refresh/'),
            statusCode: 401,
          ),
        ),
      );
      when(() => storage.delete(key: any(named: 'key'))).thenAnswer((_) async {});

      final result = await repository.refresh();

      expect(result, isA<Failure<AuthTokens>>());
      verify(() => storage.delete(key: 'auth_access_token')).called(1);
      verify(() => storage.delete(key: 'auth_refresh_token')).called(1);
    });

    test('нет refresh токена — сразу Failure без запроса', () async {
      when(() => storage.read(key: 'auth_refresh_token')).thenAnswer((_) async => null);

      final result = await repository.refresh();

      expect(result, isA<Failure<AuthTokens>>());
      verifyNever(() => dio.post('/api/token/refresh/', data: any(named: 'data')));
    });
  });
}