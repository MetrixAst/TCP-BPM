import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
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
//import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../core/network/server_config.dart';

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
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Выход из аккаунта'),
        content: const Text('Подтвердить выход из аккаунта?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Отмена'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: TextButton.styleFrom(foregroundColor: MetrixColors.danger),
            child: const Text('Подтвердить выход'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _isLoggingOut = true);

    await _logoutRepository.logout();

    if (!mounted) return;
    context.go('/login');
  }

  String? _fullAvatarUrl(String? avatarPath) {
    if (avatarPath == null || avatarPath.isEmpty) return null;
    if (avatarPath.startsWith('http')) return avatarPath;

    final baseUrl = ServerConfig.baseUrl;
    return '$baseUrl$avatarPath';
  }
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: const AppTopBar(title: 'Профиль'),
      body: _buildBody(),
      bottomNavigationBar: _isLoading ? null : _buildLogoutBar(),
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
    final employee = profile.employee;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _ProfileHeaderCard(profile: profile, avatarUrl: _fullAvatarUrl(profile.avatar)),
          const SizedBox(height: AppSpacing.xl),
          const _SectionLabel('ИНФОРМАЦИЯ'),
          const SizedBox(height: AppSpacing.sm),
          _ListGroup(
            children: [
              _InfoRow(icon: Icons.badge_outlined, label: 'Логин', value: profile.username),
              if (employee?.department != null) ...[
                const _RowDivider(),
                _InfoRow(icon: Icons.apartment_outlined, label: 'Отдел', value: employee!.department!),
              ],
              if (employee != null && employee.phone.isNotEmpty) ...[
                const _RowDivider(),
                _InfoRow(icon: Icons.phone_outlined, label: 'Телефон', value: employee.phone),
              ],
              if (employee?.status != null) ...[
                const _RowDivider(),
                _InfoRow(icon: Icons.verified_user_outlined, label: 'Статус', value: employeeStatusLabel(employee!.status)),
              ],
            ],
          ),
          const SizedBox(height: AppSpacing.xl),
          const _SectionLabel('ПОДДЕРЖКА'),
          const SizedBox(height: AppSpacing.sm),
          const _SupportGroup(),
        ],
      ),
    );
  }

  Widget _buildLogoutBar() {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.sm, AppSpacing.lg, AppSpacing.lg),
        child: AppButton(
          label: 'Выход из аккаунта',
          variant: AppButtonVariant.danger,
          icon: Icons.logout,
          isLoading: _isLoggingOut,
          onPressed: _handleLogout,
        ),
      ),
    );
  }
}

class _ProfileHeaderCard extends StatelessWidget {
  final ProfileDto profile;
  final String? avatarUrl;

  const _ProfileHeaderCard({required this.profile, this.avatarUrl});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: MetrixColors.text,
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
            color: MetrixColors.text.withValues(alpha: 0.25),
            blurRadius: 16,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        children: [
          Container(
            width: 84,
            height: 84,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: Colors.white.withValues(alpha: 0.15), width: 3),
            ),
            child: CircleAvatar(
              radius: 39,
              backgroundColor: Colors.white.withValues(alpha: 0.08),
              backgroundImage: avatarUrl != null ? NetworkImage(avatarUrl!) : null,
              child: avatarUrl == null
                  ? const Icon(Icons.person, size: 38, color: Colors.white70)
                  : null,
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          Text(
            profile.fullName,
            style: const TextStyle(color: Colors.white, fontSize: 19, fontWeight: FontWeight.w700),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(
              profile.role,
              style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600),
            ),
          ),
          if (profile.employee?.position != null) ...[
            const SizedBox(height: 8),
            Text(
              profile.employee!.position!,
              style: TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 12.5),
            ),
          ],
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w600,
        color: MetrixColors.textMuted,
        letterSpacing: 0.8,
      ),
    );
  }
}

class _ListGroup extends StatelessWidget {
  final List<Widget> children;
  const _ListGroup({required this.children});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: MetrixColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: MetrixColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(children: children),
    );
  }
}

class _RowDivider extends StatelessWidget {
  const _RowDivider();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(left: 60),
      child: Divider(height: 1, color: MetrixColors.border),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _InfoRow({required this.icon, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              color: MetrixColors.primary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(9),
            ),
            child: Icon(icon, size: 18, color: MetrixColors.primary),
          ),
          const SizedBox(width: AppSpacing.sm + 4),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(fontSize: 11.5, color: MetrixColors.textMuted)),
                const SizedBox(height: 1),
                Text(value, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: MetrixColors.text)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Коды статусов сотрудника из hr.enums.EmployeeStatusEnum.
String employeeStatusLabel(String status) => switch (status) {
      'active' => 'Активен',
      'dismissed' => 'Уволен',
      'vacation' => 'В отпуске',
      'sick_leave' => 'На больничном',
      _ => status,
    };

/// Контакты поддержки (App Store Guideline 1.5).
class SupportContacts {
  static const email = 'info@avantage.one';
  static const phones = ['+7 707 243 75 37', '+7 747 687 38 51'];
  static const pageUrl = 'https://gateway.metrix.com.ai/support';
  static const company = 'ТОО «Avantage One»';
}

class _SupportGroup extends StatelessWidget {
  const _SupportGroup();

  Future<void> _open(BuildContext context, Uri uri, String copyText) async {
    final messenger = ScaffoldMessenger.of(context);
    var opened = false;
    try {
      opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      opened = false;
    }
    if (!opened) {
      await Clipboard.setData(ClipboardData(text: copyText));
      messenger.showSnackBar(SnackBar(content: Text('Скопировано: $copyText')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final rows = <Widget>[
      _ActionRow(
        icon: Icons.mail_outline,
        label: 'Эл. почта',
        value: SupportContacts.email,
        onTap: () => _open(
          context,
          Uri(scheme: 'mailto', path: SupportContacts.email, queryParameters: {'subject': 'Metrix App'}),
          SupportContacts.email,
        ),
      ),
      for (final phone in SupportContacts.phones) ...[
        const _RowDivider(),
        _ActionRow(
          icon: Icons.call_outlined,
          label: 'Телефон',
          value: phone,
          onTap: () => _open(context, Uri(scheme: 'tel', path: phone.replaceAll(' ', '')), phone),
        ),
      ],
      const _RowDivider(),
      _ActionRow(
        icon: Icons.help_outline,
        label: 'Страница поддержки',
        value: SupportContacts.company,
        onTap: () => _open(context, Uri.parse(SupportContacts.pageUrl), SupportContacts.pageUrl),
      ),
    ];
    return _ListGroup(children: rows);
  }
}

class _ActionRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final VoidCallback onTap;

  const _ActionRow({required this.icon, required this.label, required this.value, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Row(
          children: [
            Expanded(child: _InfoRow(icon: icon, label: label, value: value)),
            const Padding(
              padding: EdgeInsets.only(right: 16),
              child: Icon(Icons.chevron_right, size: 20, color: MetrixColors.textMuted),
            ),
          ],
        ),
      ),
    );
  }
}
