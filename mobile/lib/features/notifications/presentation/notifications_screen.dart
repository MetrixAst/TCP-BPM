import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/api_result.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../data/notifications_repository.dart';
import '../data/notification_dto.dart';
import '../../push/data/deep_link_resolver.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  late final NotificationsRepository _repository;

  final List<NotificationDto> _notifications = [];
  bool _isLoading = true;
  bool _isLoadingMore = false;
  String? _errorMessage;
  int _currentPage = 1;
  bool _hasMore = true;

  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _repository = NotificationsRepository(dio: DioClient().dio);
    _scrollController.addListener(_onScroll);
    _load(reset: true);
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - 200 &&
        !_isLoadingMore &&
        _hasMore) {
      _loadMore();
    }
  }

  Future<void> _load({required bool reset}) async {
    if (reset) {
      setState(() {
        _isLoading = true;
        _errorMessage = null;
        _currentPage = 1;
        _hasMore = true;
      });
    }

    final result = await _repository.getNotifications(page: 1);

    if (!mounted) return;

    setState(() {
      _isLoading = false;
      switch (result) {
        case Success(:final data):
          _notifications
            ..clear()
            ..addAll(data.results);
          _hasMore = data.next != null;
          _currentPage = 1;
        case Failure(:final message):
          _errorMessage = message;
      }
    });
  }

  Future<void> _loadMore() async {
    setState(() => _isLoadingMore = true);

    final result = await _repository.getNotifications(page: _currentPage + 1);

    if (!mounted) return;

    setState(() {
      _isLoadingMore = false;
      switch (result) {
        case Success(:final data):
          _notifications.addAll(data.results);
          _hasMore = data.next != null;
          _currentPage += 1;
        case Failure():
          _hasMore = false;
      }
    });
  }

  Future<void> _handleTap(NotificationDto notif) async {
    if (!notif.isRead) {
      await _repository.markAsRead(notif.id);
      if (!mounted) return;
      setState(() {
        final index = _notifications.indexWhere((n) => n.id == notif.id);
        if (index != -1) {
          _notifications[index] = NotificationDto(
            id: notif.id,
            title: notif.title,
            text: notif.text,
            createdDate: notif.createdDate,
            targetType: notif.targetType,
            targetId: notif.targetId,
            url: notif.url,
            isRead: true,
          );
        }
      });
    }

    final path = resolveDeepLink(
      targetType: notif.targetType,
      targetId: notif.targetId?.toString(),
    );
    if (path != null && mounted) {
      context.push(path);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: const AppTopBar(title: 'Уведомления'),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null && _notifications.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: MetrixColors.danger, size: 40),
              const SizedBox(height: AppSpacing.sm),
              Text(_errorMessage!, style: const TextStyle(color: MetrixColors.danger), textAlign: TextAlign.center),
            ],
          ),
        ),
      );
    }

    if (_notifications.isEmpty) {
      return const Center(
        child: Text('Уведомлений нет', style: TextStyle(color: MetrixColors.textMuted)),
      );
    }

    return RefreshIndicator(
      onRefresh: () => _load(reset: true),
      child: ListView.separated(
        controller: _scrollController,
        padding: const EdgeInsets.all(AppSpacing.lg),
        itemCount: _notifications.length + (_hasMore ? 1 : 0),
        separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
        itemBuilder: (context, index) {
          if (index >= _notifications.length) {
            return const Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.md),
              child: Center(child: CircularProgressIndicator()),
            );
          }
          final notif = _notifications[index];
          return _NotificationTile(notification: notif, onTap: () => _handleTap(notif));
        },
      ),
    );
  }
}

class _NotificationTile extends StatelessWidget {
  final NotificationDto notification;
  final VoidCallback onTap;

  const _NotificationTile({required this.notification, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final isRead = notification.isRead;

    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: isRead ? MetrixColors.surface : MetrixColors.primary.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isRead ? MetrixColors.border : MetrixColors.primary.withValues(alpha: 0.4),
            width: isRead ? 1 : 1.5,
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 8,
              height: 8,
              margin: const EdgeInsets.only(top: 6, right: 10),
              decoration: BoxDecoration(
                color: isRead ? Colors.transparent : MetrixColors.primary,
                shape: BoxShape.circle,
                border: isRead ? Border.all(color: MetrixColors.border) : null,
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          notification.title,
                          style: TextStyle(
                            fontWeight: isRead ? FontWeight.w500 : FontWeight.w700,
                            fontSize: 14.5,
                            color: isRead ? MetrixColors.textMuted : MetrixColors.text,
                          ),
                        ),
                      ),
                      if (!isRead) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: MetrixColors.primary,
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: const Text(
                            'Новое',
                            style: TextStyle(fontSize: 10, color: Colors.white, fontWeight: FontWeight.w700),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 3),
                  Text(
                    notification.text,
                    style: TextStyle(
                      fontSize: 13,
                      color: isRead ? MetrixColors.textMuted.withValues(alpha: 0.7) : MetrixColors.textMuted,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    notification.createdDate,
                    style: const TextStyle(fontSize: 11, color: MetrixColors.textMuted),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}