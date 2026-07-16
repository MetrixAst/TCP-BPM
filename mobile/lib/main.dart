import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'firebase_options.dart';
import 'core/theme/theme.dart';
import 'app/router.dart';
import 'core/network/dio_client.dart';
import 'features/push/data/push_repository.dart';
import 'features/push/data/push_service.dart';
import 'features/push/data/deep_link_resolver.dart';

/// Обработчик push, пришедших когда приложение полностью закрыто (terminated)
/// или в фоне (background). Должен быть top-level функцией.
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  // Ничего дополнительно делать не нужно — система сама покажет
  // системную нотификацию по 'notification' полю сообщения.
}

final _pushService = PushService();

void _handleDeepLink(Map<String, dynamic> data) {
  final path = resolveDeepLink(
    targetType: data['target_type'] as String?,
    targetId: data['target_id'] as String?,
  );
  if (path != null) {
    router.push(path);
  }
}


void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

  FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

  FirebaseMessaging.instance.onTokenRefresh.listen((newToken) async {
    try {
      await PushRepository(dio: DioClient().dio).registerToken(newToken);
    } catch (_) {}
  });

  await _pushService.initLocalNotifications(
    onNotificationTap: (payload) {
      if (payload != null) {
        final data = PushService.decodePayload(payload);
        _handleDeepLink(data);
      }
    },
  );

  // Foreground: показываем локальную нотификацию (система сама не показывает баннер)
  _pushService.listenToMessages(
    onForegroundMessage: (message) {
      _pushService.showLocalNotification(message);
    },
    onMessageOpenedApp: (message) {
      _handleDeepLink(message.data);
    },
  );

  // Terminated: приложение было открыто нажатием на push
  final initialMessage = await _pushService.getInitialMessage();
  if (initialMessage != null) {
    // откладываем до первого кадра, чтобы GoRouter успел инициализироваться
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _handleDeepLink(initialMessage.data);
    });
  }

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