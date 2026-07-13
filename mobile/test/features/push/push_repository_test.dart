import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:metrix_app/features/push/data/push_repository.dart';

class MockDio extends Mock implements Dio {}

void main() {
  late MockDio dio;
  late PushRepository repository;

  setUp(() {
    dio = MockDio();
    repository = PushRepository(dio: dio);
  });

  group('registerToken', () {
    test('отправляет POST /devices с fcm-токеном', () async {
      when(() => dio.post('/api/v1/mobile/devices/', data: any(named: 'data')))
          .thenAnswer(
        (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/devices/'),
          statusCode: 201,
          data: {'id': 1, 'created': true},
        ),
      );

      await repository.registerToken('fcm-token-123');

      verify(() => dio.post(
            '/api/v1/mobile/devices/',
            data: {'fcm': 'fcm-token-123'},
          )).called(1);
    });

    test('повторная регистрация того же токена не выбрасывает ошибку (идемпотентно)', () async {
      when(() => dio.post('/api/v1/mobile/devices/', data: any(named: 'data')))
          .thenAnswer(
        (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/devices/'),
          statusCode: 201,
          data: {'id': 1, 'created': false},
        ),
      );

      await repository.registerToken('fcm-token-123');

      verify(() => dio.post(
            '/api/v1/mobile/devices/',
            data: {'fcm': 'fcm-token-123'},
          )).called(1);
    });
  });

  group('unregisterToken', () {
    test('отправляет DELETE /devices с fcm-токеном', () async {
      when(() => dio.delete('/api/v1/mobile/devices/', data: any(named: 'data')))
          .thenAnswer(
        (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/devices/'),
          statusCode: 200,
          data: {'deleted': 1},
        ),
      );

      await repository.unregisterToken('fcm-token-123');

      verify(() => dio.delete(
            '/api/v1/mobile/devices/',
            data: {'fcm': 'fcm-token-123'},
          )).called(1);
    });
  });
}