import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../core/network/api_result.dart';
import '../core/network/dio_client.dart';
import '../features/auth/data/auth_repository.dart';
import 'router.dart';

/// Только для съёмки стора: --dart-define=SCREENSHOT_TOUR=true
Future<void> runScreenshotTour() async {
  const user = String.fromEnvironment('SCREENSHOT_USER');
  const pass = String.fromEnvironment('SCREENSHOT_PASS');
  if (user.isEmpty || pass.isEmpty) {
    debugPrint('SCREENSHOT_TOUR: нет SCREENSHOT_USER/PASS');
    return;
  }

  final auth = AuthRepository(
    dio: DioClient().dio,
    storage: const FlutterSecureStorage(),
  );
  await auth.clear();
  await Future<void>.delayed(const Duration(seconds: 2));

  final result = await auth.login(username: user, password: pass);
  if (result is! Success) {
    debugPrint('SCREENSHOT_TOUR: login failed');
    return;
  }

  router.go('/');
  await Future<void>.delayed(const Duration(seconds: 5));
  debugPrint('SCREENSHOT_READY:05-home');
  await Future<void>.delayed(const Duration(seconds: 3));

  router.push('/rounds/today');
  await Future<void>.delayed(const Duration(seconds: 3));
  debugPrint('SCREENSHOT_READY:01-rounds');
  await Future<void>.delayed(const Duration(seconds: 3));

  try {
    final rounds = await DioClient().dio.get('/api/v1/mobile/rounds/today/');
    final list = rounds.data as List<dynamic>;
    final pick = list.cast<Map<String, dynamic>>().firstWhere(
          (r) => r['status'] == 'in_progress',
          orElse: () => list.first as Map<String, dynamic>,
        );
    router.push('/rounds/route/${pick['id']}');
    await Future<void>.delayed(const Duration(seconds: 3));
    debugPrint('SCREENSHOT_READY:02-route');
    await Future<void>.delayed(const Duration(seconds: 3));
    router.pop();
    await Future<void>.delayed(const Duration(milliseconds: 600));
    router.pop();
  } catch (e) {
    debugPrint('SCREENSHOT_TOUR: route failed $e');
    router.go('/');
  }

  await Future<void>.delayed(const Duration(seconds: 1));
  router.push('/attendance/today');
  await Future<void>.delayed(const Duration(seconds: 3));
  debugPrint('SCREENSHOT_READY:03-status');
  await Future<void>.delayed(const Duration(seconds: 3));
  router.pop();

  await Future<void>.delayed(const Duration(seconds: 1));
  router.push('/tasks');
  await Future<void>.delayed(const Duration(seconds: 3));
  debugPrint('SCREENSHOT_READY:04-tasks');
  await Future<void>.delayed(const Duration(seconds: 2));
  debugPrint('SCREENSHOT_TOUR:done');
}
