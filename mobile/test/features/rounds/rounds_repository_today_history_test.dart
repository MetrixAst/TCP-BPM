import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:metrix_app/features/rounds/data/planned_round_summary.dart';
import 'package:metrix_app/features/rounds/data/round_detail.dart';
import 'package:metrix_app/features/rounds/data/rounds_repository.dart';
import 'package:metrix_app/core/network/api_result.dart';

class MockDio extends Mock implements Dio {}

void main() {
  late MockDio dio;
  late RoundsRepository repository;

  setUp(() {
    dio = MockDio();
    repository = RoundsRepository(dio: dio);
  });

  group('getToday', () {
    test('парсит список заданий на сегодня', () async {
      when(() => dio.get('/api/v1/mobile/rounds/today/')).thenAnswer(
        (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/today/'),
          statusCode: 200,
          data: [
            {
              'id': 5,
              'route_name': 'Маршрут А',
              'status': 'pending',
              'planned_start': '2026-09-08T08:00:00+05:00',
              'planned_end': '2026-09-08T10:00:00+05:00',
              'is_overdue': true,
              'total_points': 3,
              'completed_points': 1,
            },
          ],
        ),
      );

      final result = await repository.getToday();

      expect(result, isA<Success<List<PlannedRoundSummary>>>());
      final list = (result as Success<List<PlannedRoundSummary>>).data;
      expect(list.length, 1);
      expect(list.first.routeName, 'Маршрут А');
      expect(list.first.isOverdue, isTrue);
      expect(list.first.progressPercent, 33);
    });

    test('сетевая ошибка возвращает Failure', () async {
      when(() => dio.get('/api/v1/mobile/rounds/today/')).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/today/'),
          type: DioExceptionType.connectionTimeout,
        ),
      );

      final result = await repository.getToday();

      expect(result, isA<Failure<List<PlannedRoundSummary>>>());
    });
  });

  group('getHistory', () {
    test('парсит завершённое задание с completed_at', () async {
      when(() => dio.get('/api/v1/mobile/rounds/history/')).thenAnswer(
        (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/history/'),
          statusCode: 200,
          data: [
            {
              'id': 4,
              'route_name': 'Маршрут Б',
              'status': 'completed',
              'planned_start': '2026-09-07T08:00:00+05:00',
              'planned_end': '2026-09-07T10:00:00+05:00',
              'completed_at': '2026-09-07T09:15:00+05:00',
              'is_overdue': false,
              'total_points': 2,
              'completed_points': 2,
            },
          ],
        ),
      );

      final result = await repository.getHistory();

      final list = (result as Success<List<PlannedRoundSummary>>).data;
      expect(list.first.status, 'completed');
      expect(list.first.completedAt, isNotNull);
      expect(list.first.progressPercent, 100);
    });

    test('пустая история возвращает пустой список без ошибки', () async {
      when(() => dio.get('/api/v1/mobile/rounds/history/')).thenAnswer(
        (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/history/'),
          statusCode: 200,
          data: <dynamic>[],
        ),
      );

      final result = await repository.getHistory();

      expect((result as Success<List<PlannedRoundSummary>>).data, isEmpty);
    });
  });

  group('getRouteDetail', () {
    test('парсит маршрут с точками по порядку', () async {
      when(() => dio.get('/api/v1/mobile/rounds/5/')).thenAnswer(
        (_) async => Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/5/'),
          statusCode: 200,
          data: {
            'id': 5,
            'route_name': 'Маршрут А',
            'status': 'in_progress',
            'planned_start': '2026-09-08T08:00:00+05:00',
            'planned_end': '2026-09-08T10:00:00+05:00',
            'is_overdue': false,
            'points': [
              {'order': 1, 'point_uuid': 'aaa', 'point_name': 'Точка 1', 'location': '', 'is_visited': true, 'visit_id': 10},
              {'order': 2, 'point_uuid': 'bbb', 'point_name': 'Точка 2', 'location': 'Подвал', 'is_visited': false, 'visit_id': null},
            ],
            'completed': 1,
            'total': 2,
          },
        ),
      );

      final result = await repository.getRouteDetail(5);

      expect(result, isA<Success<RoundDetail>>());
      final detail = (result as Success<RoundDetail>).data;
      expect(detail.points.length, 2);
      expect(detail.points[0].isVisited, isTrue);
      expect(detail.points[1].isVisited, isFalse);
      expect(detail.points[1].location, 'Подвал');
    });

    test('403 для чужого задания даёт понятную ошибку', () async {
      when(() => dio.get('/api/v1/mobile/rounds/5/')).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/5/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/5/'),
            statusCode: 403,
          ),
        ),
      );

      final result = await repository.getRouteDetail(5);

      expect((result as Failure<RoundDetail>).message, 'Нет доступа к этому заданию');
    });

    test('404 для несуществующего задания', () async {
      when(() => dio.get('/api/v1/mobile/rounds/999/')).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/999/'),
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/999/'),
            statusCode: 404,
          ),
        ),
      );

      final result = await repository.getRouteDetail(999);

      expect((result as Failure<RoundDetail>).message, 'Задание не найдено');
    });
  });
}
