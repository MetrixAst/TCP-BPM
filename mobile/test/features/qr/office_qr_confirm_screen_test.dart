import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metrix_app/features/qr/data/qr_scan_target.dart';
import 'package:metrix_app/features/qr/presentation/office_qr_confirm_screen.dart';

void main() {
  Widget wrap(OfficeScanTarget target) {
    return MaterialApp(home: OfficeQrConfirmScreen(target: target));
  }

  testWidgets('показывает название точки и просьбу подтвердить приход', (tester) async {
    await tester.pumpWidget(wrap(const OfficeScanTarget(
      publicId: 'abc',
      pointName: 'Главный офис',
      nextAction: 'day_start',
      alreadyDone: false,
    )));

    expect(find.text('Главный офис'), findsOneWidget);
    expect(find.text('Подтвердите приход'), findsOneWidget);
    expect(find.text('Подтвердить'), findsOneWidget);
  });

  testWidgets('для day_end показывает просьбу подтвердить уход', (tester) async {
    await tester.pumpWidget(wrap(const OfficeScanTarget(
      publicId: 'abc',
      pointName: 'Главный офис',
      nextAction: 'day_end',
      alreadyDone: false,
    )));

    expect(find.text('Подтвердите уход'), findsOneWidget);
  });

  testWidgets('alreadyDone=true сразу показывает финальное состояние без кнопки', (tester) async {
    await tester.pumpWidget(wrap(const OfficeScanTarget(
      publicId: 'abc',
      pointName: 'Главный офис',
      nextAction: null,
      alreadyDone: true,
    )));

    expect(find.text('Отметки на сегодня уже сделаны'), findsOneWidget);
    expect(find.text('Подтвердить'), findsNothing);
  });
}
