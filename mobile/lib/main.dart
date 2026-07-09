import 'package:flutter/material.dart';
import 'core/theme/theme.dart';
import 'app/router.dart';

void main() {
  runApp(const MetrixApp());
}

class MetrixApp extends StatelessWidget {
  const MetrixApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'metriX',
      theme: MetrixTheme.light(),
      routerConfig: router,
    );
  }
}