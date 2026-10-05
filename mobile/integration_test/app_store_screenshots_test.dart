import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:metrix_app/main.dart' as app;

/// Живые кадры для App Store: вход демо-аккаунтом, затем основные экраны.
/// Учётные данные только через --dart-define, в git не кладём.
void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  const user = String.fromEnvironment('SCREENSHOT_USER');
  const pass = String.fromEnvironment('SCREENSHOT_PASS');

  Future<void> shot(WidgetTester tester, String name) async {
    await tester.pumpAndSettle(const Duration(seconds: 1));
    await binding.convertFlutterSurfaceToImage();
    await tester.pumpAndSettle();
    await binding.takeScreenshot(name);
  }

  Future<void> waitFor(WidgetTester tester, Finder finder) async {
    for (var i = 0; i < 40; i++) {
      await tester.pump(const Duration(milliseconds: 250));
      if (finder.evaluate().isNotEmpty) return;
    }
    throw TestFailure('Не появилось: $finder');
  }

  testWidgets('App Store screenshots', (tester) async {
    expect(user, isNotEmpty, reason: 'SCREENSHOT_USER');
    expect(pass, isNotEmpty, reason: 'SCREENSHOT_PASS');

    app.main();
    await tester.pumpAndSettle();
    await waitFor(tester, find.text('Войти'));

    final fields = find.byType(TextFormField);
    expect(fields, findsNWidgets(2));
    await tester.enterText(fields.at(0), user);
    await tester.enterText(fields.at(1), pass);
    await tester.tap(find.text('Войти'));
    await tester.pump();
    await waitFor(tester, find.text('РАЗДЕЛЫ'));
    await tester.pumpAndSettle(const Duration(seconds: 2));

    await shot(tester, '05-home');

    await tester.tap(find.text('Обходы'));
    await waitFor(tester, find.text('Обходы на сегодня'));
    await tester.pumpAndSettle(const Duration(seconds: 2));
    await shot(tester, '01-rounds');

    final route = find.textContaining('Ежедневный контроль');
    if (route.evaluate().isNotEmpty) {
      await tester.tap(route.first);
      await tester.pumpAndSettle(const Duration(seconds: 2));
      await shot(tester, '02-route');
      await tester.pageBack();
      await tester.pumpAndSettle();
    }

    await tester.pageBack();
    await tester.pumpAndSettle();
    await waitFor(tester, find.text('Статус дня'));

    await tester.tap(find.text('Статус дня'));
    await waitFor(tester, find.text('Статус за сегодня'));
    await tester.pumpAndSettle(const Duration(seconds: 2));
    await shot(tester, '03-status');

    await tester.pageBack();
    await tester.pumpAndSettle();

    await tester.tap(find.text('Мои задачи'));
    await tester.pumpAndSettle(const Duration(seconds: 2));
    await shot(tester, '04-tasks');
  });
}
