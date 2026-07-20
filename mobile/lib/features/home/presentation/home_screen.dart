import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../profile/data/logout_repository.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _unreadCount = 0;
  bool _hasFinanceAccess = false;
  String? _userName;
  String? _userRole;

  @override
  void initState() {
    super.initState();
    _loadMe();
    _checkFinanceAccess();
  }

  Future<void> _loadMe() async {
    try {
      final response = await DioClient().dio.get('/api/v1/mobile/me/');

      final badges = response.data['badges'] as Map<String, dynamic>;
      final counts = badges['counts'] as Map<String, dynamic>;
      final total = counts.values.fold<int>(0, (sum, v) => sum + (v as int));

      final profile = response.data['profile'] as Map<String, dynamic>;

      if (mounted) {
        setState(() {
          _unreadCount = total;
          _userName = profile['full_name'] as String?;
          _userRole = profile['role'] as String?;
        });
      }
    } catch (_) {}
  }

  Future<void> _checkFinanceAccess() async {
    try {
      await DioClient().dio.get('/api/v1/finances/payments/', queryParameters: {'page': 1});
      if (mounted) setState(() => _hasFinanceAccess = true);
    } catch (_) {
      if (mounted) setState(() => _hasFinanceAccess = false);
    }
  }

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

  Future<void> _handleScanQr(BuildContext context) async {
    final result = await context.push<String>('/qr-scanner');
    if (result != null && context.mounted) {
      context.push('/tickets/create?room=${Uri.encodeComponent(result)}');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBody: true,
      backgroundColor: MetrixColors.surfaceMuted,
      body: SafeArea(
        bottom: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: AppSpacing.lg),
              _buildHeader(context),
              const SizedBox(height: AppSpacing.xl),
              const _SectionLabel('РАЗДЕЛЫ'),
              const SizedBox(height: AppSpacing.sm),
              _ListGroup(
                children: [
                  _ListRow(
                    icon: Icons.checklist_rounded,
                    title: 'Статус дня',
                    subtitle: 'Мои отметки за сегодня',
                    onTap: () => context.push('/attendance/today'),
                  ),
                  const _RowDivider(),
                  _ListRow(
                    icon: Icons.build_outlined,
                    title: 'Заявки',
                    subtitle: 'Список обращений',
                    onTap: () => context.push('/tickets'),
                  ),
                  const _RowDivider(),
                  _ListRow(
                    icon: Icons.checklist_rtl_outlined,
                    title: 'Мои задачи',
                    subtitle: 'Список поручений',
                    onTap: () => context.push('/tasks'),
                  ),
                  if (_hasFinanceAccess) ...[
                    const _RowDivider(),
                    _ListRow(
                      icon: Icons.attach_money_rounded,
                      title: 'Финансы',
                      subtitle: 'Платежи и календарь',
                      onTap: () => context.push('/finances'),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: AppSpacing.xl),
            ],
          ),
        ),
      ),
      bottomNavigationBar: _BottomBar(
        onCheckin: () => context.push('/checkin'),
        onScanQr: () => _handleScanQr(context),
        onCreateTicket: () => context.push('/tickets/create'),
        onProfile: () => context.push('/profile'),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            color: MetrixColors.text,
            borderRadius: BorderRadius.circular(12),
          ),
          alignment: Alignment.center,
          child: RichText(
            text: const TextSpan(
              style: TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w700, fontSize: 16),
              children: [
                TextSpan(text: 'm', style: TextStyle(color: Colors.white)),
                TextSpan(text: 'X', style: TextStyle(color: MetrixColors.primary)),
              ],
            ),
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _userName ?? '...',
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: MetrixColors.text),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 1),
              Text(
                _userRole ?? '',
                style: const TextStyle(fontSize: 13, color: MetrixColors.textMuted),
              ),
            ],
          ),
        ),
        Stack(
          clipBehavior: Clip.none,
          children: [
            _HeaderIconButton(
              icon: Icons.notifications_outlined,
              onTap: () async {
                await context.push('/notifications');
                _loadMe();
              },
            ),
            if (_unreadCount > 0)
              Positioned(
                top: -4,
                right: -4,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                  constraints: const BoxConstraints(minWidth: 18),
                  decoration: BoxDecoration(
                    color: MetrixColors.danger,
                    borderRadius: BorderRadius.circular(9),
                    border: Border.all(color: MetrixColors.surfaceMuted, width: 2),
                  ),
                  child: Text(
                    _unreadCount > 9 ? '9+' : '$_unreadCount',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w700),
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(width: AppSpacing.sm),
        _HeaderIconButton(
          icon: Icons.logout_rounded,
          iconColor: MetrixColors.danger,
          onTap: () => _logout(context),
        ),
      ],
    );
  }
}

class _BottomBar extends StatelessWidget {
  final VoidCallback onCheckin;
  final VoidCallback onScanQr;
  final VoidCallback onCreateTicket;
  final VoidCallback onProfile;

  const _BottomBar({
    required this.onCheckin,
    required this.onScanQr,
    required this.onCreateTicket,
    required this.onProfile,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(AppSpacing.lg, 0, AppSpacing.lg, 14),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 8),
          decoration: BoxDecoration(
            color: MetrixColors.surface.withValues(alpha: 0.92),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: MetrixColors.border.withValues(alpha: 0.7)),
            boxShadow: [
              BoxShadow(
                color: MetrixColors.text.withValues(alpha: 0.08),
                blurRadius: 20,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _BottomBarItem(icon: Icons.camera_alt_outlined, label: 'Чек-ин', onTap: onCheckin),
              _BottomBarItem(icon: Icons.qr_code_scanner_rounded, label: 'Скан QR', onTap: onScanQr),
              _BottomBarItem(icon: Icons.add_circle_outline, label: 'Заявка', onTap: onCreateTicket),
              _BottomBarItem(icon: Icons.person_outline_rounded, label: 'Профиль', onTap: onProfile),
            ],
          ),
        ),
      ),
    );
  }
}

class _BottomBarItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _BottomBarItem({required this.icon, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 21, color: MetrixColors.textMuted),
            const SizedBox(height: 3),
            Text(label, style: const TextStyle(fontSize: 10, color: MetrixColors.textMuted, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}

class _HeaderIconButton extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final VoidCallback onTap;

  const _HeaderIconButton({
    required this.icon,
    this.iconColor = MetrixColors.text,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: MetrixColors.surface,
      borderRadius: BorderRadius.circular(11),
      child: InkWell(
        borderRadius: BorderRadius.circular(11),
        onTap: onTap,
        child: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            border: Border.all(color: MetrixColors.border),
            borderRadius: BorderRadius.circular(11),
          ),
          child: Icon(icon, size: 18, color: iconColor),
        ),
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

class _ListRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback onTap;

  const _ListRow({
    required this.icon,
    required this.title,
    this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
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
                  Text(
                    title,
                    style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600, color: MetrixColors.text),
                  ),
                  if (subtitle != null) ...[
                    const SizedBox(height: 1),
                    Text(subtitle!, style: const TextStyle(fontSize: 12.5, color: MetrixColors.textMuted)),
                  ],
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded, size: 20, color: MetrixColors.textMuted),
          ],
        ),
      ),
    );
  }
}