import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:metrix_app/features/profile/data/profile_repository.dart';
import 'package:metrix_app/features/profile/data/profile_dto.dart';
import 'package:metrix_app/core/network/api_result.dart';

class MockDio extends Mock implements Dio {}

void main() {
  late MockDio dio;
  late ProfileRepository repository;

  setUp(() {
    dio = MockDio();
    repository = ProfileRepository(dio: dio);
  });

  group('getProfile', () {
    test('успешный ответ парсится в ProfileDto', () async {
      when(() => dio.get('/api/v1/mobile/me/')).thenAnswer(
        (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/me/'),
          statusCode: 200,
          data: {
            'profile': {
              'id': 12,
              'username': 'user_administrator',
              'full_name': 'Иван Иванов',
              'role': 'administrator',
              'email': '',
              'avatar': '/media/uploads/avatar.png',
              'employee': {
                'department': 'Коммерческий блок',
                'position': 'Менеджер по аренде',
                'status': 'active',
                'phone': '+77010000007',
                'hire_date': '2024-10-14',
                'head': true,
              },
            },
            'menu': [],
            'badges': {},
          },
        ),
      );

      final result = await repository.getProfile();

      expect(result, isA<Success<ProfileDto>>());
      final profile = (result as Success<ProfileDto>).data;
      expect(profile.fullName, 'Иван Иванов');
      expect(profile.role, 'administrator');
      expect(profile.employee?.position, 'Менеджер по аренде');
    });

    test('профиль без employee (employee: null) парсится корректно', () async {
      when(() => dio.get('/api/v1/mobile/me/')).thenAnswer(
        (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/me/'),
          statusCode: 200,
          data: {
            'profile': {
              'id': 5,
              'username': 'guest1',
              'full_name': 'guest1',
              'role': 'guest',
              'email': '',
              'avatar': null,
              'employee': null,
            },
            'menu': [],
            'badges': {},
          },
        ),
      );

      final result = await repository.getProfile();

      expect(result, isA<Success<ProfileDto>>());
      final profile = (result as Success<ProfileDto>).data;
      expect(profile.employee, isNull);
      expect(profile.avatar, isNull);
    });

    test('401 возвращает Failure с понятным сообщением', () async {
      when(() => dio.get('/api/v1/mobile/me/')).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/mobile/me/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/mobile/me/'),
            statusCode: 401,
          ),
        ),
      );

      final result = await repository.getProfile();

      expect(result, isA<Failure<ProfileDto>>());
      final failure = result as Failure<ProfileDto>;
      expect(failure.statusCode, 401);
    });

    test('сетевая ошибка (timeout) возвращает Failure', () async {
      when(() => dio.get('/api/v1/mobile/me/')).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/mobile/me/'),
          type: DioExceptionType.connectionTimeout,
        ),
      );

      final result = await repository.getProfile();

      expect(result, isA<Failure<ProfileDto>>());
    });
  });
}