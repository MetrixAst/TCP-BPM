import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/api_result.dart';
import '../data/profile_dto.dart';
import '../data/profile_repository.dart';
import '../data/logout_repository.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  late final ProfileRepository _profileRepository;
  late final LogoutRepository _logoutRepository;

  bool _isLoading = true;
  bool _isLoggingOut = false;
  String? _errorMessage;
  ProfileDto? _profile;

  @override
  void initState() {
    super.initState();
    final dio = DioClient().dio;
    const storage = FlutterSecureStorage();
    _profileRepository = ProfileRepository(dio: dio);
    _logoutRepository = LogoutRepository(dio: dio, storage: storage);
    _loadProfile();
  }

  Future<void> _loadProfile() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final result = await _profileRepository.getProfile();

    if (!mounted) return;

    switch (result) {
      case Success(:final data):
        setState(() {
          _profile = data;
          _isLoading = false;
        });
      case Failure(:final message):
        setState(() {
          _errorMessage = message;
          _isLoading = false;
        });
    }
  }

  Future<void> _handleLogout() async {
    setState(() => _isLoggingOut = true);

    await _logoutRepository.logout();

    if (!mounted) return;
    context.go('/login');
  }

  String? _fullAvatarUrl(String? avatarPath) {
    if (avatarPath == null || avatarPath.isEmpty) return null;
    if (avatarPath.startsWith('http')) return avatarPath;

    final baseUrl = DioClient().dio.options.baseUrl;
    return '$baseUrl$avatarPath';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Профиль')),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_errorMessage!, style: const TextStyle(color: Colors.red)),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loadProfile,
              child: const Text('Повторить'),
            ),
          ],
        ),
      );
    }

    final profile = _profile!;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          CircleAvatar(
            radius: 48,
            backgroundImage: _fullAvatarUrl(profile.avatar) != null
                ? NetworkImage(_fullAvatarUrl(profile.avatar)!)
                : null,
            child: _fullAvatarUrl(profile.avatar) == null
                ? const Icon(Icons.person, size: 48)
                : null,
          ),
          const SizedBox(height: 16),
          Text(
            profile.fullName,
            style: Theme.of(context).textTheme.titleLarge,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(
            profile.role,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          if (profile.employee?.position != null) ...[
            const SizedBox(height: 4),
            Text(
              profile.employee!.position!,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: _isLoggingOut ? null : _handleLogout,
              child: _isLoggingOut
                  ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
                  : const Text('Выйти'),
            ),
          ),
        ],
      ),
    );
  }
}