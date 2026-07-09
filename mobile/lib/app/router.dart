import 'package:go_router/go_router.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../features/auth/presentation/login_screen.dart';
import '../features/home/presentation/home_screen.dart';

const _storage = FlutterSecureStorage();

final router = GoRouter(
  initialLocation: '/',
  redirect: (context, state) async {
    final token = await _storage.read(key: 'auth_access_token'); // было 'auth_token'
    final loggingIn = state.matchedLocation == '/login';

    if (token == null && !loggingIn) return '/login';
    if (token != null && loggingIn) return '/';
    return null;
  },
  routes: [
    GoRoute(path: '/', builder: (context, state) => const HomeScreen()),
    GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
  ],
);