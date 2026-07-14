import 'package:flutter/material.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../data/attendance_repository.dart';
import '../data/attendance_today_status.dart';
import '../../../core/network/api_result.dart';

class TodayStatusScreen extends StatefulWidget {
  const TodayStatusScreen({super.key});

  @override
  State<TodayStatusScreen> createState() => _TodayStatusScreenState();
}

class _TodayStatusScreenState extends State<TodayStatusScreen> {
  late final AttendanceRepository _repository;

  bool _isLoading = true;
  String? _errorMessage;
  List<AttendanceTodayStatus>? _statuses;

  @override
  void initState() {
    super.initState();
    _repository = AttendanceRepository(dio: DioClient().dio);
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final result = await _repository.getToday();

    if (!mounted) return;

    switch (result) {
      case Success(:final data):
        setState(() {
          _statuses = data;
          _isLoading = false;
        });
      case Failure(:final message):
        setState(() {
          _errorMessage = message;
          _isLoading = false;
        });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: const AppTopBar(title: 'Статус за сегодня'),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null) {
      return ListView(
        children: [
          const SizedBox(height: 120),
          const Icon(Icons.error_outline, color: MetrixColors.danger, size: 40),
          const SizedBox(height: AppSpacing.sm),
          Text(_errorMessage!, style: const TextStyle(color: MetrixColors.danger), textAlign: TextAlign.center),
        ],
      );
    }

    final statuses = _statuses!;
    final completedCount = statuses.where((s) => s.isCompleted).length;

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        AppCard(
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: MetrixColors.primary.withValues(alpha: 0.1),
                  shape: BoxShape.circle,
                ),
                alignment: Alignment.center,
                child: Text(
                  '$completedCount/4',
                  style: const TextStyle(fontWeight: FontWeight.w700, color: MetrixColors.primary, fontSize: 14),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              const Expanded(
                child: Text(
                  'Отметок сделано сегодня',
                  style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        for (final status in statuses) ...[
          _StatusRow(status: status),
          const SizedBox(height: AppSpacing.sm),
        ],
      ],
    );
  }
}

class _StatusRow extends StatelessWidget {
  final AttendanceTodayStatus status;

  const _StatusRow({required this.status});

  @override
  Widget build(BuildContext context) {
    final done = status.isCompleted;

    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: InkWell(
        onTap: done && status.photoUrl != null
            ? () => _openPhoto(context, status.photoUrl!, status.type.label)
            : null,
        child: Row(
          children: [
            if (done && status.photoUrl != null)
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: Image.network(
                  status.photoUrl!,
                  width: 44,
                  height: 44,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => _fallbackIcon(done),
                ),
              )
            else
              _fallbackIcon(done),
            const SizedBox(width: AppSpacing.sm + 4),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    status.type.label,
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5),
                  ),
                  const SizedBox(height: 1),
                  Text(
                    done ? status.time! : 'Ещё не отмечено',
                    style: TextStyle(
                      fontSize: 12.5,
                      color: done ? MetrixColors.textMuted : MetrixColors.textMuted.withValues(alpha: 0.7),
                    ),
                  ),
                ],
              ),
            ),
            if (done)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: MetrixColors.accent.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Text(
                  'Готово',
                  style: TextStyle(fontSize: 11, color: MetrixColors.accent, fontWeight: FontWeight.w600),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _fallbackIcon(bool done) {
    return Container(
      width: 44,
      height: 44,
      decoration: BoxDecoration(
        color: done
            ? MetrixColors.accent.withValues(alpha: 0.1)
            : MetrixColors.textMuted.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Icon(
        done ? Icons.check_rounded : Icons.schedule_rounded,
        size: 18,
        color: done ? MetrixColors.accent : MetrixColors.textMuted,
      ),
    );
  }

  void _openPhoto(BuildContext context, String url, String title) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => _PhotoViewerScreen(url: url, title: title),
      ),
    );
  }
}

class _PhotoViewerScreen extends StatelessWidget {
  final String url;
  final String title;

  const _PhotoViewerScreen({required this.url, required this.title});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(title),
      ),
      body: Center(
        child: InteractiveViewer(
          child: Image.network(
            url,
            errorBuilder: (_, __, ___) => const Icon(Icons.broken_image, color: Colors.white54, size: 64),
          ),
        ),
      ),
    );
  }
}