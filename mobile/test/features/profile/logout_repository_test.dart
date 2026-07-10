import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:metrix_app/features/profile/data/logout_repository.dart';

class MockDio extends Mock implements Dio {}

class MockSecureStorage extends Mock implements FlutterSecureStorage {}

void main() {
  late MockDio dio;
  late MockSecureStorage storage;
  late LogoutRepository repository;

  setUp(() {
    dio = MockDio();
    storage = MockSecureStorage();
    repository = LogoutRepository(dio: dio, storage: storage);
  });

  test('успешный logout вызывает DELETE /devices и чистит storage', () async {
    when(() => dio.delete('/api/v1/mobile/devices/')).thenAnswer(
      (_) async => Response(
        requestOptions: RequestOptions(path: '/api/v1/mobile/devices/'),
        statusCode: 200,
        data: {'deleted': 1},
      ),
    );
    when(() => storage.delete(key: any(named: 'key'))).thenAnswer((_) async {});

    await repository.logout();

    verify(() => dio.delete('/api/v1/mobile/devices/')).called(1);
    verify(() => storage.delete(key: 'auth_access_token')).called(1);
    verify(() => storage.delete(key: 'auth_refresh_token')).called(1);
  });

  test('сетевая ошибка при DELETE не мешает очистке storage', () async {
    when(() => dio.delete('/api/v1/mobile/devices/')).thenThrow(
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
}