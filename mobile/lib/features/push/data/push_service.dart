import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class PushService {
  final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();

  Future<String?> getToken() async {
    await _messaging.requestPermission();
    return _messaging.getToken();
  }

  void onTokenRefresh(void Function(String token) callback) {
    _messaging.onTokenRefresh.listen(callback);
  }

  /// Инициализация локальных нотификаций (для показа баннера в foreground)
  Future<void> initLocalNotifications({
    required void Function(String? payload) onNotificationTap,
  }) async {
    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosSettings = DarwinInitializationSettings();
    const settings = InitializationSettings(android: androidSettings, iOS: iosSettings);

    await _localNotifications.initialize(
      settings,
      onDidReceiveNotificationResponse: (response) {
        onNotificationTap(response.payload);
      },
    );

    const androidChannel = AndroidNotificationChannel(
      'metrix_default_channel',
      'metriX уведомления',
      description: 'Основной канал уведомлений metriX',
      importance: Importance.high,
    );

    await _localNotifications
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(androidChannel);
  }

  /// Показывает системный баннер, когда push пришёл в foreground
  /// (Firebase Messaging сам этого не делает).
  Future<void> showLocalNotification(RemoteMessage message) async {
    final notification = message.notification;
    if (notification == null) return;

    const androidDetails = AndroidNotificationDetails(
      'metrix_default_channel',
      'metriX уведомления',
      channelDescription: 'Основной канал уведомлений metriX',
      importance: Importance.high,
      priority: Priority.high,
    );
    const iosDetails = DarwinNotificationDetails();
    const details = NotificationDetails(android: androidDetails, iOS: iosDetails);

    await _localNotifications.show(
      message.hashCode,
      notification.title,
      notification.body,
      details,
      payload: _encodePayload(message.data),
    );
  }

  /// Кодирует data-payload в строку для передачи через flutter_local_notifications
  String _encodePayload(Map<String, dynamic> data) {
    return Uri(queryParameters: data.map((k, v) => MapEntry(k, v.toString()))).query;
  }

  /// Декодирует строку обратно в Map
  static Map<String, String> decodePayload(String payload) {
    return Uri.splitQueryString(payload);
  }

  /// Подписки на все три состояния получения push
  void listenToMessages({
    required void Function(RemoteMessage message) onForegroundMessage,
    required void Function(RemoteMessage message) onMessageOpenedApp,
  }) {
    FirebaseMessaging.onMessage.listen(onForegroundMessage);
    FirebaseMessaging.onMessageOpenedApp.listen(onMessageOpenedApp);
  }

  /// Проверяет, было ли приложение открыто через нажатие на push
  /// (terminated state)
  Future<RemoteMessage?> getInitialMessage() {
    return _messaging.getInitialMessage();
  }
}