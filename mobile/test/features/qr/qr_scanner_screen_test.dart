import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metrix_app/features/qr/presentation/qr_scanner_screen.dart';

const _permissionsChannel = MethodChannel('flutter.baseflow.com/permissions/methods');
const _cameraPermission = 1;

void _mockCameraStatus(int status) {
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
    _permissionsChannel,
    (call) async => switch (call.method) {
      'checkPermissionStatus' => status,
      'requestPermissions' => {_cameraPermission: status},
      _ => null,
    },
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_permissionsChannel, null);
  });

  testWidgets('без разрешения на камеру показывает просьбу разрешить, а не ошибку', (tester) async {
    _mockCameraStatus(0);
    await tester.pumpWidget(const MaterialApp(home: QrScannerScreen()));
    await tester.pumpAndSettle();

    expect(find.text('Разрешить доступ'), findsOneWidget);
    expect(find.textContaining('Нет доступа к камере'), findsOneWidget);
    expect(find.text('Выбрать фото QR из галереи'), findsOneWidget);
    expect(find.textContaining('unexpected'), findsNothing);
  });

  testWidgets('если камера не стартует, пробует заднюю и фронтальную и предлагает фото', (tester) async {
    _mockCameraStatus(1);
    const scannerChannel = MethodChannel('dev.steenbakker.mobile_scanner/scanner/method');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    final facings = <int>[];
    messenger.setMockMethodCallHandler(scannerChannel, (call) async {
      switch (call.method) {
        case 'state':
          return 1;
        case 'start':
          facings.add((call.arguments as Map)['facing'] as int);
          throw PlatformException(code: 'MOBILE_SCANNER_GENERIC_ERROR');
      }
      return null;
    });
    messenger.setMockStreamHandler(
      const EventChannel('dev.steenbakker.mobile_scanner/scanner/event'),
      MockStreamHandler.inline(onListen: (_, __) {}),
    );
    addTearDown(() => messenger.setMockMethodCallHandler(scannerChannel, null));

    await tester.pumpWidget(const MaterialApp(home: QrScannerScreen()));
    for (var i = 0; i < 20; i++) {
      await tester.pump(const Duration(seconds: 1));
    }

    expect(facings, [1, 1, 0, 0]);
    expect(find.text('Сфотографировать QR'), findsOneWidget);
    expect(find.text('Код: MOBILE_SCANNER_GENERIC_ERROR'), findsOneWidget);
  });

  testWidgets('при запрете «больше не спрашивать» ведёт в настройки', (tester) async {
    _mockCameraStatus(4);
    await tester.pumpWidget(const MaterialApp(home: QrScannerScreen()));
    await tester.pumpAndSettle();

    expect(find.text('Открыть настройки'), findsOneWidget);
    expect(find.textContaining('запрещён'), findsOneWidget);
  });
}
