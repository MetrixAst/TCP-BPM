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

  testWidgets('при запрете «больше не спрашивать» ведёт в настройки', (tester) async {
    _mockCameraStatus(4);
    await tester.pumpWidget(const MaterialApp(home: QrScannerScreen()));
    await tester.pumpAndSettle();

    expect(find.text('Открыть настройки'), findsOneWidget);
    expect(find.textContaining('запрещён'), findsOneWidget);
  });
}
