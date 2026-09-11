import 'package:flutter_test/flutter_test.dart';
import 'package:metrix_app/features/qr/data/qr_router_repository.dart';

void main() {
  group('extractQrUuid', () {
    test('достаёт UUID из полного веб-URL точки обхода', () {
      final result = extractQrUuid('https://app.metrix/ecopark/rounds/scan/e0ebdf6e-6b4f-4a4f-8cfb-bbfd5f2ab5ff/');
      expect(result, 'e0ebdf6e-6b4f-4a4f-8cfb-bbfd5f2ab5ff');
    });

    test('достаёт UUID из голой строки', () {
      final result = extractQrUuid('087fd4d6-e01c-48e9-8307-b4a49e943470');
      expect(result, '087fd4d6-e01c-48e9-8307-b4a49e943470');
    });

    test('возвращает null для строки без UUID', () {
      expect(extractQrUuid('какой-то текст без кода'), isNull);
    });

    test('регистронезависимо (заглавные буквы в UUID)', () {
      final result = extractQrUuid('https://x/y/E0EBDF6E-6B4F-4A4F-8CFB-BBFD5F2AB5FF/');
      expect(result, 'E0EBDF6E-6B4F-4A4F-8CFB-BBFD5F2AB5FF');
    });
  });
}
