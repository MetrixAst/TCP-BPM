import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:metrix_app/features/rounds/data/round_item_answer.dart';
import 'package:metrix_app/features/rounds/data/round_point_detail.dart';
import 'package:metrix_app/features/rounds/data/rounds_repository.dart';
import 'package:metrix_app/core/network/api_result.dart';

class MockDio extends Mock implements Dio {}

class FakeFormData extends Fake implements FormData {}

void main() {
  setUpAll(() {
    registerFallbackValue(FakeFormData());
  });

  late MockDio dio;
  late RoundsRepository repository;

  setUp(() {
    dio = MockDio();
    repository = RoundsRepository(dio: dio);
  });

  group('getPointDetail', () {
    const uuid = 'e0ebdf6e-6b4f-4a4f-8cfb-bbfd5f2ab5ff';

    test('возвращает точку с чек-листом', () async {
      when(() => dio.get('/api/v1/mobile/rounds/points/$uuid/')).thenAnswer(
        (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/points/$uuid/'),
          statusCode: 200,
          data: {
            'point_uuid': uuid,
            'point_name': 'Насосная',
            'location': 'Подвал',
            'items': [
              {'id': 1, 'text': 'Огнетушитель на месте', 'requires_photo_on_fail': true},
              {'id': 2, 'text': 'Освещение работает', 'requires_photo_on_fail': false},
            ],
            'already_visited': false,
          },
        ),
      );

      final result = await repository.getPointDetail(uuid);

      expect(result, isA<Success<RoundPointDetail>>());
      final detail = (result as Success<RoundPointDetail>).data;
      expect(detail.pointName, 'Насосная');
      expect(detail.items.length, 2);
      expect(detail.items.first.requiresPhotoOnFail, isTrue);
      expect(detail.alreadyVisited, isFalse);
    });

    test('404 — точка не найдена', () async {
      when(() => dio.get('/api/v1/mobile/rounds/points/$uuid/')).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/points/$uuid/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/points/$uuid/'),
            statusCode: 404,
          ),
        ),
      );

      final result = await repository.getPointDetail(uuid);

      expect(result, isA<Failure<RoundPointDetail>>());
      expect((result as Failure<RoundPointDetail>).message, 'Точка не найдена');
    });

    test('403 — нет профиля сотрудника', () async {
      when(() => dio.get('/api/v1/mobile/rounds/points/$uuid/')).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/points/$uuid/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/points/$uuid/'),
            statusCode: 403,
          ),
        ),
      );

      final result = await repository.getPointDetail(uuid);

      expect((result as Failure<RoundPointDetail>).message, 'Профиль сотрудника не найден');
    });
  });

  group('submitPointAnswer', () {
    const uuid = 'e0ebdf6e-6b4f-4a4f-8cfb-bbfd5f2ab5ff';

    test('успешная отправка возвращает Success', () async {
      when(() => dio.post(
        '/api/v1/mobile/rounds/7/points/$uuid/answer/',
        data: any(named: 'data'),
        options: any(named: 'options'),
      )).thenAnswer(
        (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/7/points/$uuid/answer/'),
          statusCode: 201,
          data: {'success': true, 'already_done': false, 'message': 'Точка отмечена'},
        ),
      );

      final result = await repository.submitPointAnswer(
        plannedRoundId: 7,
        pointUuid: uuid,
        answers: const [RoundItemAnswer(itemId: 1, passed: true)],
      );

      expect(result, isA<Success<Map<String, dynamic>>>());
    });

    test('нет назначенного обхода — понятная 403 ошибка', () async {
      when(() => dio.post(
        '/api/v1/mobile/rounds/7/points/$uuid/answer/',
        data: any(named: 'data'),
        options: any(named: 'options'),
      )).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/7/points/$uuid/answer/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/7/points/$uuid/answer/'),
            statusCode: 403,
            data: {'error': 'Задание не найдено или нет доступа'},
          ),
        ),
      );

      final result = await repository.submitPointAnswer(
        plannedRoundId: 7,
        pointUuid: uuid,
        answers: const [RoundItemAnswer(itemId: 1, passed: false, comment: 'Сломан')],
      );

      expect(result, isA<Failure<Map<String, dynamic>>>());
      expect((result as Failure<Map<String, dynamic>>).message, 'Задание не найдено или нет доступа');
    });
  });
}
