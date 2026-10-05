import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';

import '../core/database/app_database.dart';
import '../core/database/outbox_repository.dart';
import '../core/database/sync_worker.dart';
import '../core/network/dio_client.dart';
import '../features/attendance/data/attendance_repository.dart';
import '../features/push/data/deep_link_resolver.dart';
import '../features/push/data/push_repository.dart';
import '../features/push/data/push_service.dart';
import '../features/tasks/data/tasks_repository.dart';
import '../features/tickets/data/ticket_detail_repository.dart';
import '../firebase_options.dart';
import 'router.dart';

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

@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
}

Future<void> initializeNativeServices() async {
  try {
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

    _pushService.listenToMessages(
      onForegroundMessage: (message) {
        _pushService.showLocalNotification(message);
      },
      onMessageOpenedApp: (message) {
        _handleDeepLink(message.data);
      },
    );

    final initialMessage = await _pushService.getInitialMessage();
    if (initialMessage != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _handleDeepLink(initialMessage.data);
      });
    }

    final db = AppDatabase.instance;
    final outboxRepo = OutboxRepository(db: db);
    final syncWorker = SyncWorker(
      outboxRepo: outboxRepo,
      attendanceRepo: AttendanceRepository(dio: DioClient().dio),
      ticketRepo: TicketDetailRepository(dio: DioClient().dio),
      tasksRepo: TasksRepository(dio: DioClient().dio),
    );
    syncWorker.startListening();
    syncWorker.syncNow();
  } catch (error, stackTrace) {
    FlutterError.reportError(
      FlutterErrorDetails(
        exception: error,
        stack: stackTrace,
        library: 'app initialization',
      ),
    );
  }
}
