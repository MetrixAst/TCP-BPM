import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:metrix_app/features/attendance/data/attendance_repository.dart';
import 'package:metrix_app/core/network/api_result.dart';

class MockDio extends Mock implements Dio {}

class FakeFormData extends Fake implements FormData {}

void main() {
  setUpAll(() {
    registerFallbackValue(FakeFormData());
  });

  late MockDio dio;
  late AttendanceRepository repository;
  late File testPhoto;

  setUp(() {
    dio = MockDio();
    repository = AttendanceRepository(dio: dio);
    // Создаём реальный временный файл — MultipartFile.fromFile читает байты с диска
    testPhoto = File('${Directory.systemTemp.path}/test_photo_${DateTime.now().microsecondsSinceEpoch}.jpg')
      ..writeAsBytesSync([0xFF, 0xD8, 0xFF, 0xE0]); // минимальный JPEG-заголовок
  });

  tearDown(() {
    if (testPhoto.existsSync()) {
      testPhoto.deleteSync();
    }
  });

  group('checkin', () {
    test('успешный чек-ин возвращает Success', () async {
      when(() => dio.post(
        '/api/v1/mobile/attendance/checkin/',
        data: any(named: 'data'),
      )).thenAnswer(
            (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/attendance/checkin/'),
          statusCode: 201,
          data: {
            'id': 1,
            'event_type': 'day_start',
            'timestamp': '13.07.2026, 09:00',
            'location_address': 'Almaty',
          },
        ),
      );

      final result = await repository.checkin(
        eventType: 'day_start',
        photo: testPhoto,
        latitude: 43.238,
        longitude: 76.945,
      );

      expect(result, isA<Success<void>>());
      verify(() => dio.post(
        '/api/v1/mobile/attendance/checkin/',
        data: any(named: 'data'),
      )).called(1);
    });

    test('дублирующий чек-ин (400) возвращает Failure с текстом сервера', () async {
      when(() => dio.post(
        '/api/v1/mobile/attendance/checkin/',
        data: any(named: 'data'),
      )).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/mobile/attendance/checkin/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/mobile/attendance/checkin/'),
            statusCode: 400,
            data: {'error': "Событие 'Приход' уже зафиксировано на сегодня."},
          ),
        ),
      );

      final result = await repository.checkin(
        eventType: 'day_start',
        photo: testPhoto,
      );

      expect(result, isA<Failure<void>>());
      final failure = result as Failure<void>;
      expect(failure.message, "Событие 'Приход' уже зафиксировано на сегодня.");
      expect(failure.statusCode, 400);
    });

    test('403 без профиля сотрудника возвращает понятное сообщение', () async {
      when(() => dio.post(
        '/api/v1/mobile/attendance/checkin/',
        data: any(named: 'data'),
      )).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/mobile/attendance/checkin/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/mobile/attendance/checkin/'),
            statusCode: 403,
          ),
        ),
      );

      final result = await repository.checkin(
        eventType: 'day_start',
        photo: testPhoto,
      );

      expect(result, isA<Failure<void>>());
      final failure = result as Failure<void>;
      expect(failure.message, 'Профиль сотрудника не найден');
    });

    test('сетевой таймаут возвращает Failure', () async {
      when(() => dio.post(
        '/api/v1/mobile/attendance/checkin/',
        data: any(named: 'data'),
      )).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/mobile/attendance/checkin/'),
          type: DioExceptionType.connectionTimeout,
        ),
      );

      final result = await repository.checkin(
        eventType: 'day_start',
        photo: testPhoto,
      );

      expect(result, isA<Failure<void>>());
    });

    test('работает без координат (гео опционально)', () async {
      when(() => dio.post(
        '/api/v1/mobile/attendance/checkin/',
        data: any(named: 'data'),
      )).thenAnswer(
            (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/attendance/checkin/'),
          statusCode: 201,
          data: {
            'id': 2,
            'event_type': 'day_start',
            'timestamp': '13.07.2026, 09:00',
            'location_address': '',
          },
        ),
      );

      final result = await repository.checkin(
        eventType: 'day_start',
        photo: testPhoto,
      );

      expect(result, isA<Success<void>>());
    });
  });

  group('getToday', () {
    test('возвращает список отметок за сегодня', () async {
      when(() => dio.get('/api/v1/mobile/attendance/today/')).thenAnswer(
            (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/attendance/today/'),
          statusCode: 200,
          data: {
            'marks': [
              {'type': 'day_start', 'time': '2026-07-13T09:00:00+05:00'},
            ],
          },
        ),
      );

      final result = await repository.getToday();

      expect(result, isA<Success<List<dynamic>>>());
    });

    test('пустой список, если отметок ещё нет', () async {
      when(() => dio.get('/api/v1/mobile/attendance/today/')).thenAnswer(
            (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/attendance/today/'),
          statusCode: 200,
          data: {'marks': []},
        ),
      );

      final result = await repository.getToday();

      expect(result, isA<Success<List<dynamic>>>());
      final success = result as Success<List<dynamic>>;
      expect(success.data, isEmpty);
    });
  });
}