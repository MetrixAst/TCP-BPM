import 'dart:io';

import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() async {
  await integrationDriver(
    onScreenshot: (String name, List<int> bytes, [Map<String, Object?>? args]) async {
      final file = File('$name.png');
      await file.writeAsBytes(bytes);
      stdout.writeln('Wrote ${file.absolute.path} (${bytes.length} bytes)');
      return true;
    },
  );
}
