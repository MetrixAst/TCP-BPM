import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/presentation/login_screen.dart';
import '../features/home/presentation/home_screen.dart';
import '../features/profile/presentation/profile_screen.dart';
import '../features/attendance/presentation/today_status_screen.dart';
import '../features/tasks/presentation/tasks_list_screen.dart';
import '../features/notifications/presentation/notifications_screen.dart';
import '../features/rounds/presentation/rounds_today_screen.dart';
import '../features/rounds/presentation/rounds_history_screen.dart';
import '../features/rounds/presentation/route_detail_screen.dart';
import '../features/finances/presentation/finances_screen.dart';

const _storage = FlutterSecureStorage();
final rootNavigatorKey = GlobalKey<NavigatorState>();

class _WebOnlyScreen extends StatelessWidget {
  const _WebOnlyScreen({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'Этот раздел в веб-демо ограничен.\nОткройте нативное приложение для камеры, QR и офлайн-очереди.',
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}

final router = GoRouter(
  navigatorKey: rootNavigatorKey,
  initialLocation: '/',
  redirect: (context, state) async {
    final token = await _storage.read(key: 'auth_access_token');
    final loggingIn = state.matchedLocation == '/login';

    if (token == null && !loggingIn) return '/login';
    if (token != null && loggingIn) return '/';
    return null;
  },
  routes: [
    GoRoute(path: '/', builder: (context, state) => const HomeScreen()),
    GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
    GoRoute(path: '/profile', builder: (context, state) => const ProfileScreen()),
    GoRoute(
      path: '/checkin',
      builder: (context, state) => const _WebOnlyScreen(title: 'Отметка'),
    ),
    GoRoute(path: '/attendance/today', builder: (context, state) => const TodayStatusScreen()),
    GoRoute(
      path: '/tickets',
      builder: (context, state) => const _WebOnlyScreen(title: 'Заявки'),
    ),
    GoRoute(
      path: '/tickets/create',
      builder: (context, state) => const _WebOnlyScreen(title: 'Новая заявка'),
    ),
    GoRoute(
      path: '/tickets/:id',
      builder: (context, state) => const _WebOnlyScreen(title: 'Заявка'),
    ),
    GoRoute(path: '/tasks', builder: (context, state) => const TasksListScreen()),
    GoRoute(
      path: '/tasks/:id',
      builder: (context, state) => const _WebOnlyScreen(title: 'Задача'),
    ),
    GoRoute(path: '/notifications', builder: (context, state) => const NotificationsScreen()),
    GoRoute(
      path: '/qr-scanner',
      builder: (context, state) => const _WebOnlyScreen(title: 'QR'),
    ),
    GoRoute(
      path: '/attendance/office-confirm',
      builder: (context, state) => const _WebOnlyScreen(title: 'Офис QR'),
    ),
    GoRoute(
      path: '/rounds/point-confirm',
      builder: (context, state) => const _WebOnlyScreen(title: 'Точка обхода'),
    ),
    GoRoute(path: '/rounds/today', builder: (context, state) => const RoundsTodayScreen()),
    GoRoute(path: '/rounds/history', builder: (context, state) => const RoundsHistoryScreen()),
    GoRoute(
      path: '/rounds/route/:id',
      builder: (context, state) {
        final id = int.parse(state.pathParameters['id']!);
        return RouteDetailScreen(plannedRoundId: id);
      },
    ),
    GoRoute(path: '/finances', builder: (context, state) => const FinancesScreen()),
  ],
);
