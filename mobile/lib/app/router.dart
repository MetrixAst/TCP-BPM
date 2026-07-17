import 'package:go_router/go_router.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter/material.dart';

import '../features/auth/presentation/login_screen.dart';
import '../features/home/presentation/home_screen.dart';
import '../features/profile/presentation/profile_screen.dart';
import '../features/attendance/presentation/checkin_screen.dart';
import '../features/attendance/presentation/today_status_screen.dart';
import '../features/tickets/presentation/tickets_list_screen.dart';
import '../features/tickets/presentation/create_ticket_screen.dart';
import '../features/tickets/presentation/ticket_detail_screen.dart';
import '../features/tasks/presentation/tasks_list_screen.dart';
import '../features/tasks/presentation/task_detail_screen.dart';
import '../features/notifications/presentation/notifications_screen.dart';
import '../features/qr/presentation/qr_scanner_screen.dart';


const _storage = FlutterSecureStorage();
final rootNavigatorKey = GlobalKey<NavigatorState>();
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
    GoRoute(path: '/checkin', builder: (context, state) => const CheckinScreen()),
    GoRoute(path: '/attendance/today', builder: (context, state) => const TodayStatusScreen()),
    GoRoute(path: '/tickets', builder: (context, state) => const TicketsListScreen()),
    GoRoute(
      path: '/tickets/create',
      builder: (context, state) {
        final room = state.uri.queryParameters['room'];
        return CreateTicketScreen(prefilledRoom: room);
      },
    ),
    GoRoute(
      path: '/tickets/:id',
      builder: (context, state) {
        final id = int.parse(state.pathParameters['id']!);
        return TicketDetailScreen(ticketId: id);
      },
    ),
    GoRoute(path: '/tasks', builder: (context, state) => const TasksListScreen()),
    GoRoute(
      path: '/tasks/:id',
      builder: (context, state) {
        final id = int.parse(state.pathParameters['id']!);
        return TaskDetailScreen(taskId: id);
      },
    ),

    GoRoute(path: '/notifications', builder: (context, state) => const NotificationsScreen()),
    GoRoute(path: '/qr-scanner', builder: (context, state) => const QrScannerScreen()),
  ],
);