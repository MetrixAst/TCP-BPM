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

  @override
  void initState() {
    super.initState();
    _loadUnreadCount();
  }

  Future<void> _loadUnreadCount() async {
    try {
      final response = await DioClient().dio.get('/api/v1/mobile/me/');
      final badges = response.data['badges'] as Map<String, dynamic>;
      final counts = badges['counts'] as Map<String, dynamic>;
      final total = counts.values.fold<int>(0, (sum, v) => sum + (v as int));
      if (mounted) setState(() => _unreadCount = total);
    } catch (_) {}
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

  String _greeting() {
    final hour = DateTime.now().hour;
    if (hour < 6) return 'Доброй ночи';
    if (hour < 12) return 'Доброе утро';
    if (hour < 18) return 'Добрый день';
    return 'Добрый вечер';
  }

  String _formattedDate() {
    const months = [
      'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
      'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
    ];
    final now = DateTime.now();
    return '${now.day} ${months[now.month - 1]}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: AppSpacing.lg),
              Row(
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
                          _greeting(),
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: MetrixColors.text,
                          ),
                        ),
                        const SizedBox(height: 1),
                        Text(
                          _formattedDate(),
                          style: const TextStyle(fontSize: 13, color: MetrixColors.textMuted),
                        ),
                      ],
                    ),
                  ),
                  Stack(
                    clipBehavior: Clip.none,
                    children: [
                      Material(
                        color: MetrixColors.surface,
                        borderRadius: BorderRadius.circular(11),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(11),
                          onTap: () async {
                            await context.push('/notifications');
                            _loadUnreadCount();
                          },
                          child: Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              border: Border.all(color: MetrixColors.border),
                              borderRadius: BorderRadius.circular(11),
                            ),
                            child: const Icon(Icons.notifications_outlined, size: 18, color: MetrixColors.text),
                          ),
                        ),
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
                  Material(
                    color: MetrixColors.surface,
                    borderRadius: BorderRadius.circular(11),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(11),
                      onTap: () => _logout(context),
                      child: Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          border: Border.all(color: MetrixColors.border),
                          borderRadius: BorderRadius.circular(11),
                        ),
                        child: const Icon(Icons.logout_rounded, size: 18, color: MetrixColors.danger),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.xl),
              const _SectionLabel('РАЗДЕЛЫ'),
              const SizedBox(height: AppSpacing.sm),
              _ListGroup(
                children: [
                  _ListRow(
                    icon: Icons.person_outline_rounded,
                    title: 'Профиль',
                    subtitle: 'Личные данные',
                    onTap: () => context.push('/profile'),
                  ),
                  const _RowDivider(),
                  _ListRow(
                    icon: Icons.camera_alt_outlined,
                    title: 'Чек-ин',
                    subtitle: 'Отметка посещаемости',
                    onTap: () => context.push('/checkin'),
                  ),
                  const _RowDivider(),
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
                ],
              ),
              const SizedBox(height: AppSpacing.xl),
            ],
          ),
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