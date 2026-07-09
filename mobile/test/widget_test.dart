import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metrix_app/main.dart';

void main() {
  testWidgets('App builds without crash', (WidgetTester tester) async {
    await tester.pumpWidget(const MetrixApp());
    await tester.pump();

    expect(find.byType(MaterialApp), findsOneWidget);
  });
}