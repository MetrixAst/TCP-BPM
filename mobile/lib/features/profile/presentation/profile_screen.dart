import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/api_result.dart';
import '../data/profile_dto.dart';
import '../data/profile_repository.dart';
import '../data/logout_repository.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_button.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_top_bar.dart';

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
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: const AppTopBar(title: 'Профиль'),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: MetrixColors.danger, size: 40),
              const SizedBox(height: AppSpacing.sm),
              Text(_errorMessage!, style: const TextStyle(color: MetrixColors.danger), textAlign: TextAlign.center),
              const SizedBox(height: AppSpacing.md),
              AppButton(label: 'Повторить', variant: AppButtonVariant.secondary, onPressed: _loadProfile),
            ],
          ),
        ),
      );
    }

    final profile = _profile!;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        children: [
          AppCard(
            child: Column(
              children: [
                CircleAvatar(
                  radius: 44,
                  backgroundColor: MetrixColors.surfaceMuted,
                  backgroundImage: _fullAvatarUrl(profile.avatar) != null
                      ? NetworkImage(_fullAvatarUrl(profile.avatar)!)
                      : null,
                  child: _fullAvatarUrl(profile.avatar) == null
                      ? const Icon(Icons.person, size: 44, color: MetrixColors.textMuted)
                      : null,
                ),
                const SizedBox(height: AppSpacing.md),
                Text(profile.fullName, style: Theme.of(context).textTheme.titleLarge, textAlign: TextAlign.center),
                const SizedBox(height: AppSpacing.xs),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: MetrixColors.primary.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    profile.role,
                    style: const TextStyle(color: MetrixColors.primary, fontSize: 12, fontWeight: FontWeight.w600),
                  ),
                ),
                if (profile.employee?.position != null) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Text(profile.employee!.position!, style: const TextStyle(color: MetrixColors.textMuted, fontSize: 13)),
                ],
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          AppButton(
            label: 'Выйти',
            variant: AppButtonVariant.danger,
            icon: Icons.logout,
            isLoading: _isLoggingOut,
            onPressed: _handleLogout,
          ),
        ],
      ),
    );
  }
}