import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:metrix_app/core/database/local_data_cleaner.dart';
import 'package:metrix_app/features/profile/data/logout_repository.dart';
import 'package:metrix_app/features/push/data/push_service.dart';

class MockDio extends Mock implements Dio {}

class MockSecureStorage extends Mock implements FlutterSecureStorage {}

class MockPushService extends Mock implements PushService {}

class MockLocalDataCleaner extends Mock implements LocalDataCleaner {}

void main() {
  late MockDio dio;
  late MockSecureStorage storage;
  late MockPushService pushService;
  late MockLocalDataCleaner cleaner;
  late LogoutRepository repository;

  setUp(() {
    dio = MockDio();
    storage = MockSecureStorage();
    pushService = MockPushService();
    cleaner = MockLocalDataCleaner();
    repository = LogoutRepository(
      dio: dio,
      storage: storage,
      pushService: pushService,
      localDataCleaner: cleaner,
    );

    when(() => cleaner.clear()).thenAnswer((_) async {});
  });

  test('успешный logout отвязывает fcm-токен и чистит storage', () async {
    when(() => pushService.getToken()).thenAnswer((_) async => 'fcm-token-123');
    when(() => dio.delete('/api/v1/mobile/devices/', data: any(named: 'data')))
        .thenAnswer(
      (_) async => Response(
        requestOptions: RequestOptions(path: '/api/v1/mobile/devices/'),
        statusCode: 200,
        data: {'deleted': 1},
      ),
    );
    when(() => storage.delete(key: any(named: 'key'))).thenAnswer((_) async {});

    await repository.logout();

    verify(() => dio.delete(
          '/api/v1/mobile/devices/',
          data: {'fcm': 'fcm-token-123'},
        )).called(1);
    verify(() => storage.delete(key: 'auth_access_token')).called(1);
    verify(() => storage.delete(key: 'auth_refresh_token')).called(1);
  });

  test('нет fcm-токена -> DELETE без data, storage всё равно чистится', () async {
    when(() => pushService.getToken()).thenAnswer((_) async => null);
    when(() => dio.delete('/api/v1/mobile/devices/')).thenAnswer(
      (_) async => Response(
        requestOptions: RequestOptions(path: '/api/v1/mobile/devices/'),
        statusCode: 200,
        data: {'deleted': 0},
      ),
    );
    when(() => storage.delete(key: any(named: 'key'))).thenAnswer((_) async {});

    await repository.logout();

    verify(() => dio.delete('/api/v1/mobile/devices/')).called(1);
    verify(() => storage.delete(key: 'auth_access_token')).called(1);
    verify(() => storage.delete(key: 'auth_refresh_token')).called(1);
  });

  test('сетевая ошибка при DELETE не мешает очистке storage', () async {
    when(() => pushService.getToken()).thenAnswer((_) async => 'fcm-token-123');
    when(() => dio.delete('/api/v1/mobile/devices/', data: any(named: 'data')))
        .thenThrow(
      DioException(
        requestOptions: RequestOptions(path: '/api/v1/mobile/devices/'),
        type: DioExceptionType.connectionTimeout,
      ),
    );
    when(() => storage.delete(key: any(named: 'key'))).thenAnswer((_) async {});

    await repository.logout();

    verify(() => storage.delete(key: 'auth_access_token')).called(1);
    verify(() => storage.delete(key: 'auth_refresh_token')).called(1);
  });

  test('logout удаляет офлайн-кэш и неотправленную очередь', () async {
    when(() => pushService.getToken()).thenAnswer((_) async => null);
    when(() => dio.delete('/api/v1/mobile/devices/')).thenAnswer(
      (_) async => Response(
        requestOptions: RequestOptions(path: '/api/v1/mobile/devices/'),
        statusCode: 200,
      ),
    );
    when(() => storage.delete(key: any(named: 'key'))).thenAnswer((_) async {});

    await repository.logout();

    verify(() => cleaner.clear()).called(1);
  });

  test('сбой очистки кэша не оставляет пользователя залогиненным', () async {
    when(() => pushService.getToken()).thenAnswer((_) async => null);
    when(() => dio.delete('/api/v1/mobile/devices/')).thenAnswer(
      (_) async => Response(
        requestOptions: RequestOptions(path: '/api/v1/mobile/devices/'),
        statusCode: 200,
      ),
    );
    when(() => storage.delete(key: any(named: 'key'))).thenAnswer((_) async {});
    when(() => cleaner.clear()).thenThrow(Exception('disk error'));

    await repository.logout();

    verify(() => storage.delete(key: 'auth_access_token')).called(1);
    verify(() => storage.delete(key: 'auth_refresh_token')).called(1);
  });
}