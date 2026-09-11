import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metrix_app/features/rounds/data/planned_round_summary.dart';
import 'package:metrix_app/features/rounds/presentation/widgets/round_summary_card.dart';

void main() {
  PlannedRoundSummary buildSummary({
    String status = 'pending',
    bool isOverdue = false,
    int total = 4,
    int completed = 1,
  }) {
    return PlannedRoundSummary(
      id: 1,
      routeName: 'Маршрут А',
      status: status,
      plannedStart: DateTime(2026, 9, 8, 8, 0),
      plannedEnd: DateTime(2026, 9, 8, 10, 0),
      isOverdue: isOverdue,
      totalPoints: total,
      completedPoints: completed,
    );
  }

  Widget wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

  testWidgets('показывает название, прогресс и время', (tester) async {
    await tester.pumpWidget(wrap(RoundSummaryCard(round: buildSummary())));

    expect(find.text('Маршрут А'), findsOneWidget);
    expect(find.text('08:00 — 10:00'), findsOneWidget);
    expect(find.text('1 / 4 точек'), findsOneWidget);
  });

  testWidgets('просроченное задание показывает бейдж "Просрочен"', (tester) async {
    await tester.pumpWidget(wrap(RoundSummaryCard(round: buildSummary(isOverdue: true))));
    expect(find.text('Просрочен'), findsOneWidget);
  });

  testWidgets('завершённое задание показывает бейдж "Завершён"', (tester) async {
    await tester.pumpWidget(wrap(RoundSummaryCard(round: buildSummary(status: 'completed', completed: 4))));
    expect(find.text('Завершён'), findsOneWidget);
    expect(find.text('4 / 4 точек'), findsOneWidget);
  });

  testWidgets('тап вызывает onTap', (tester) async {
    var tapped = false;
    await tester.pumpWidget(wrap(RoundSummaryCard(round: buildSummary(), onTap: () => tapped = true)));

    await tester.tap(find.byType(RoundSummaryCard));
    await tester.pump();

    expect(tapped, isTrue);
  });
}
