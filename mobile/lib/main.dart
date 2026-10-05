import 'dart:async';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import 'app/native_bootstrap.dart';
import 'app/router.dart';
import 'app/screenshot_tour.dart';
import 'core/theme/theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MetrixApp());
  // Keep screenshot tour behind a compile-time flag, but never call
  // fromEnvironment in a non-const expression (breaks Flutter web).
  const screenshotTour = bool.fromEnvironment('SCREENSHOT_TOUR');
  if (screenshotTour) {
    unawaited(runScreenshotTour());
  } else if (!kIsWeb) {
    unawaited(initializeNativeServices());
  }
}

class MetrixApp extends StatelessWidget {
  const MetrixApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'metriX',
      debugShowCheckedModeBanner: false,
      theme: MetrixTheme.light(),
      routerConfig: router,
    );
  }
}
