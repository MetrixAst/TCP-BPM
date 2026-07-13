import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'firebase_options.dart';
import 'core/theme/theme.dart';
import 'app/router.dart';
import 'core/network/dio_client.dart';
import 'features/push/data/push_repository.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

  FirebaseMessaging.instance.onTokenRefresh.listen((newToken) async {
    try {
      await PushRepository(dio: DioClient().dio).registerToken(newToken);
    } catch (_) {}
  });

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