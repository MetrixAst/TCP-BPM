import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:metrix_app/features/qr/data/qr_router_repository.dart';
import 'package:metrix_app/features/qr/data/qr_scan_target.dart';
import 'package:metrix_app/core/network/api_result.dart';

class MockDio extends Mock implements Dio {}

void main() {
  late MockDio dio;
  late QrRouterRepository repository;

  setUp(() {
    dio = MockDio();
    repository = QrRouterRepository(dio: dio);
  });

  group('room QR — не должен трогать сеть (парсится на клиенте)', () {
    test('metrix://room/<map_id> распознаётся без похода на сервер', () async {
      final result = await repository.resolve('metrix://room/A-101');

      expect(result, isA<Success<QrScanTarget>>());
      final target = (result as Success<QrScanTarget>).data;
      expect(target, isA<RoomScanTarget>());
      expect((target as RoomScanTarget).mapId, 'A-101');
      verifyNever(() => dio.get(any(), queryParameters: any(named: 'queryParameters')));
    });
  });

  group('office/round QR — тип определяет сервер', () {
    test('офисный QR (полный URL) резолвится в OfficeScanTarget', () async {
      const uuid = '087fd4d6-e01c-48e9-8307-b4a49e943470';
      when(() => dio.get(
        '/api/v1/mobile/rounds/resolve/',
        queryParameters: {'qr': uuid},
      )).thenAnswer((_) async => Response(
        requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/resolve/'),
        statusCode: 200,
        data: {
          'type': 'office_checkin',
          'point_name': 'Офис',
          'next_action': 'day_start',
          'already_done': false,
        },
      ));

      final result = await repository.resolve('https://app.metrix/hr/attendance/office-qr/$uuid/');

      expect(result, isA<Success<QrScanTarget>>());
      final target = (result as Success<QrScanTarget>).data as OfficeScanTarget;
      expect(target.publicId, uuid);
      expect(target.pointName, 'Офис');
      expect(target.nextAction, 'day_start');
      expect(target.alreadyDone, isFalse);
    });

    test('QR точки обхода (голый UUID) резолвится в RoundScanTarget', () async {
      const uuid = 'e0ebdf6e-6b4f-4a4f-8cfb-bbfd5f2ab5ff';
      when(() => dio.get(
        '/api/v1/mobile/rounds/resolve/',
        queryParameters: {'qr': uuid},
      )).thenAnswer((_) async => Response(
        requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/resolve/'),
        statusCode: 200,
        data: {
          'type': 'round_point',
          'point_name': 'Насосная',
          'point_uuid': uuid,
          'planned_round_id': 7,
        },
      ));

      final result = await repository.resolve(uuid);

      expect(result, isA<Success<QrScanTarget>>());
      final target = (result as Success<QrScanTarget>).data as RoundScanTarget;
      expect(target.pointUuid, uuid);
      expect(target.pointName, 'Насосная');
      expect(target.plannedRoundId, 7);
    });

    test('точка обхода без назначенного на сегодня плана — planned_round_id null', () async {
      const uuid = 'e0ebdf6e-6b4f-4a4f-8cfb-bbfd5f2ab5ff';
      when(() => dio.get(
        '/api/v1/mobile/rounds/resolve/',
        queryParameters: {'qr': uuid},
      )).thenAnswer((_) async => Response(
        requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/resolve/'),
        statusCode: 200,
        data: {
          'type': 'round_point',
          'point_name': 'Насосная',
          'point_uuid': uuid,
          'planned_round_id': null,
        },
      ));

      final result = await repository.resolve(uuid);

      final target = (result as Success<QrScanTarget>).data as RoundScanTarget;
      expect(target.plannedRoundId, isNull);
    });

    test('404 от сервера — понятная ошибка "QR-код не распознан"', () async {
      const uuid = 'e0ebdf6e-6b4f-4a4f-8cfb-bbfd5f2ab5ff';
      when(() => dio.get(
        '/api/v1/mobile/rounds/resolve/',
        queryParameters: {'qr': uuid},
      )).thenThrow(DioException(
        requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/resolve/'),
        response: Response(
          requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/resolve/'),
          statusCode: 404,
        ),
      ));

      final result = await repository.resolve(uuid);

      expect(result, isA<Failure<QrScanTarget>>());
      expect((result as Failure<QrScanTarget>).message, 'QR-код не распознан');
    });

    test('таймаут сети — понятное сообщение, не падение', () async {
      const uuid = 'e0ebdf6e-6b4f-4a4f-8cfb-bbfd5f2ab5ff';
      when(() => dio.get(
        '/api/v1/mobile/rounds/resolve/',
        queryParameters: {'qr': uuid},
      )).thenThrow(DioException(
        requestOptions: RequestOptions(path: '/api/v1/mobile/rounds/resolve/'),
        type: DioExceptionType.connectionTimeout,
      ));

      final result = await repository.resolve(uuid);

      expect(result, isA<Failure<QrScanTarget>>());
      expect((result as Failure<QrScanTarget>).message, 'Сервер не отвечает, проверьте соединение');
    });
  });

  group('нераспознанный формат', () {
    test('произвольный текст без UUID и без room-схемы — ошибка без похода на сервер', () async {
      final result = await repository.resolve('какой-то мусор');

      expect(result, isA<Failure<QrScanTarget>>());
      expect((result as Failure<QrScanTarget>).message, 'QR-код не распознан');
      verifyNever(() => dio.get(any(), queryParameters: any(named: 'queryParameters')));
    });
  });
}
