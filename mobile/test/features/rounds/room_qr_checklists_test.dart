import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:metrix_app/core/network/api_result.dart';
import 'package:metrix_app/features/qr/data/qr_router_repository.dart';
import 'package:metrix_app/features/qr/data/qr_scan_target.dart';
import 'package:metrix_app/features/rounds/data/round_point_detail.dart';
import 'package:metrix_app/features/rounds/data/round_point_report.dart';
import 'package:metrix_app/features/rounds/data/rounds_repository.dart';
import 'package:metrix_app/features/rounds/presentation/round_point_confirm_screen.dart';
import 'package:metrix_app/features/rounds/presentation/round_point_report_screen.dart';

class MockDio extends Mock implements Dio {}

class MockRoundsRepository extends Mock implements RoundsRepository {}

const _uuid = 'e0ebdf6e-6b4f-4a4f-8cfb-bbfd5f2ab5ff';

Response<dynamic> _ok(String path, Object data) =>
    Response(requestOptions: RequestOptions(path: path), statusCode: 200, data: data);

RoundPointDetail _detail({int? checklistId, String? checklistName, required List<String> items}) {
  return RoundPointDetail(
    pointUuid: _uuid,
    pointName: 'Венткамера 1',
    location: '',
    checklistId: checklistId,
    checklistName: checklistName,
    checklists: const [
      RoundChecklistOption(id: 1, name: 'Общий осмотр'),
      RoundChecklistOption(id: 2, name: 'Сантехника венткамеры'),
    ],
    items: [
      for (var i = 0; i < items.length; i++)
        RoundChecklistItem(id: checklistId! * 10 + i, text: items[i], requiresPhotoOnFail: false),
    ],
    alreadyVisited: false,
  );
}

void main() {
  test('resolve: руководитель получает доступ к отчёту', () async {
    final dio = MockDio();
    when(() => dio.get('/api/v1/mobile/rounds/resolve/', queryParameters: {'qr': _uuid})).thenAnswer(
      (_) async => _ok('/resolve/', {
        'type': 'round_point',
        'point_name': 'Венткамера 1',
        'point_uuid': _uuid,
        'planned_round_id': null,
        'can_visit': false,
        'can_view_report': true,
        'checklists': [],
      }),
    );

    final result = await QrRouterRepository(dio: dio).resolve('https://bpm/ecopark/rounds/scan/$_uuid/');

    final target = (result as Success<QrScanTarget>).data as RoundScanTarget;
    expect(target.canVisit, isFalse);
    expect(target.canViewReport, isTrue);
  });

  test('getPointDetail передаёт выбранный чек-лист и читает варианты', () async {
    final dio = MockDio();
    when(() => dio.get('/api/v1/mobile/rounds/points/$_uuid/', queryParameters: {'checklist': 2})).thenAnswer(
      (_) async => _ok('/points/', {
        'point_uuid': _uuid,
        'point_name': 'Венткамера 1',
        'location': '',
        'checklist_id': 2,
        'checklist_name': 'Сантехника венткамеры',
        'checklists': [
          {'id': 1, 'name': 'Общий осмотр'},
          {'id': 2, 'name': 'Сантехника венткамеры'},
        ],
        'items': [
          {'id': 5, 'text': 'Нет протечек', 'requires_photo_on_fail': true},
        ],
        'already_visited': false,
      }),
    );

    final result = await RoundsRepository(dio: dio).getPointDetail(_uuid, checklistId: 2);

    final detail = (result as Success<RoundPointDetail>).data;
    expect(detail.checklistId, 2);
    expect(detail.checklists.map((c) => c.name), ['Общий осмотр', 'Сантехника венткамеры']);
    expect(detail.items.single.text, 'Нет протечек');
  });

  testWidgets('сотрудник с двумя чек-листами сначала выбирает, какой проходит', (tester) async {
    final repository = MockRoundsRepository();
    when(() => repository.getPointDetail(_uuid, checklistId: null)).thenAnswer(
      (_) async => Success(_detail(checklistId: 1, checklistName: 'Общий осмотр', items: ['Дверь закрыта'])),
    );
    when(() => repository.getPointDetail(_uuid, checklistId: 2)).thenAnswer(
      (_) async => Success(_detail(checklistId: 2, checklistName: 'Сантехника венткамеры', items: ['Нет протечек'])),
    );

    await tester.pumpWidget(MaterialApp(
      home: RoundPointConfirmScreen(
        repository: repository,
        target: const RoundScanTarget(pointUuid: _uuid, pointName: 'Венткамера 1', plannedRoundId: null),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Выберите, какой чек-лист проходите'), findsOneWidget);
    expect(find.text('Дверь закрыта'), findsNothing);

    await tester.tap(find.text('Сантехника венткамеры'));
    await tester.pumpAndSettle();

    expect(find.text('Нет протечек'), findsOneWidget);
    expect(find.text('Сменить'), findsOneWidget);
  });

  testWidgets('отчёт показывает проверки по чек-листам и неисправности', (tester) async {
    final repository = MockRoundsRepository();
    when(() => repository.getPointReport(_uuid)).thenAnswer(
      (_) async => Success(RoundPointReport.fromJson({
        'point_name': 'Венткамера 1',
        'location': 'Подвал',
        'is_overdue': true,
        'checklists': [
          {
            'checklist_name': 'Сантехника венткамеры',
            'assignee': 'Сантехник (Эксплуатация)',
            'interval_hours': 24,
            'is_overdue': false,
            'last_visit_at': '2026-11-11T09:00:00Z',
            'last_visit_by': 'Иван Петров',
          },
          {
            'checklist_name': 'Электрика венткамеры',
            'assignee': 'Электрик (Эксплуатация)',
            'interval_hours': 24,
            'is_overdue': true,
            'last_visit_at': null,
            'last_visit_by': null,
          },
        ],
        'open_defects': [
          {
            'id': 1,
            'description': 'Течёт кран',
            'checklist_name': 'Сантехника венткамеры',
            'created_at': '2026-11-11T09:00:00Z',
            'reported_by': 'Иван Петров',
          },
        ],
        'recent_visits': [],
      })),
    );

    await tester.pumpWidget(MaterialApp(
      home: RoundPointReportScreen(pointUuid: _uuid, pointName: 'Венткамера 1', repository: repository),
    ));
    await tester.pumpAndSettle();

    // Название чек-листа: в карточке проверки и у неисправности.
    expect(find.text('Сантехника венткамеры'), findsNWidgets(2));
    expect(find.text('В графике'), findsOneWidget);
    expect(find.text('Просрочено'), findsOneWidget);
    expect(find.text('Ещё не проверяли'), findsOneWidget);
    expect(find.text('Течёт кран'), findsOneWidget);
  });
}
