import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../../core/network/dio_client.dart';
import '../../profile/data/logout_repository.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  Future<void> _logout(BuildContext context) async {
    final logoutRepository = LogoutRepository(
      dio: DioClient().dio,
      storage: const FlutterSecureStorage(),
    );
    await logoutRepository.logout();

    if (context.mounted) {
      context.go('/login');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Home screen (заглушка)'),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () => context.push('/profile'),
              child: const Text('Профиль'),
            ),
            ElevatedButton(
              onPressed: () => context.push('/checkin'),
              child: const Text('Чек-ин'),
            ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: () => _logout(context),
              child: const Text('Выйти'),
            ),
          ],
        ),
      ),
    );
  }
}