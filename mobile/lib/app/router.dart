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

const _storage = FlutterSecureStorage();

final router = GoRouter(
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
    GoRoute(path: '/tickets/create', builder: (context, state) => const CreateTicketScreen()),
    GoRoute(
      path: '/tickets/:id',
      builder: (context, state) => Scaffold(
        appBar: AppBar(title: Text('Заявка #${state.pathParameters['id']}')),
        body: const Center(child: Text('Детали заявки (следующий тикет)')),
      ),
    ),
  ],
);