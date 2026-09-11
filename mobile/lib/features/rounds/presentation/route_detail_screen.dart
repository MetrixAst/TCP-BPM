import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/api_result.dart';
import '../../../core/network/dio_client.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../qr/data/qr_router_repository.dart';
import '../../qr/data/qr_scan_target.dart';
import '../data/round_detail.dart';
import '../data/rounds_repository.dart';
import 'widgets/round_summary_card.dart';

/// Экран маршрута планового обхода: точки по порядку, статус посещения,
/// тап по непосещённой точке требует реально отсканировать её QR (сверяем
/// UUID из скана с UUID точки в списке — по названию в списке дойти до
/// чужой/неправильной точки нельзя), только потом открывается чек-лист.
class RouteDetailScreen extends StatefulWidget {
  final int plannedRoundId;

  const RouteDetailScreen({super.key, required this.plannedRoundId});

  @override
  State<RouteDetailScreen> createState() => _RouteDetailScreenState();
}

class _RouteDetailScreenState extends State<RouteDetailScreen> {
  late final RoundsRepository _repository;
  bool _isLoading = true;
  String? _error;
  RoundDetail? _detail;

  @override
  void initState() {
    super.initState();
    _repository = RoundsRepository(dio: DioClient().dio);
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    final result = await _repository.getRouteDetail(widget.plannedRoundId);
    if (!mounted) return;
    setState(() {
      _isLoading = false;
      switch (result) {
        case Success(:final data):
          _detail = data;
        case Failure(:final message):
          _error = message;
      }
    });
  }

  Future<void> _openPoint(RoundRoutePoint point) async {
    if (point.isVisited) return;

    final rawValue = await context.push<String>('/qr-scanner');
    if (rawValue == null || !mounted) return;

    final scannedUuid = extractQrUuid(rawValue);
    if (scannedUuid != point.pointUuid) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Это QR другой точки — отсканируйте «${point.pointName}»')),
      );
      return;
    }

    await context.push(
      '/rounds/point-confirm',
      extra: RoundScanTarget(
        pointUuid: point.pointUuid,
        pointName: point.pointName,
        plannedRoundId: widget.plannedRoundId,
      ),
    );
    if (!mounted) return;
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: AppTopBar(title: _detail?.routeName ?? 'Маршрут'),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline_rounded, size: 40, color: MetrixColors.danger),
              const SizedBox(height: AppSpacing.sm),
              Text(_error!, style: const TextStyle(color: MetrixColors.danger), textAlign: TextAlign.center),
              const SizedBox(height: AppSpacing.sm),
              TextButton(onPressed: _load, child: const Text('Повторить')),
            ],
          ),
        ),
      );
    }

    final detail = _detail!;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  formatTimeRange(detail.plannedStart, detail.plannedEnd),
                  style: const TextStyle(fontSize: 12, color: MetrixColors.textMuted),
                ),
                const SizedBox(height: AppSpacing.sm),
                ClipRRect(
                  borderRadius: BorderRadius.circular(999),
                  child: LinearProgressIndicator(
                    value: detail.total == 0 ? 0 : detail.completed / detail.total,
                    minHeight: 6,
                    backgroundColor: MetrixColors.surfaceMuted,
                    valueColor: const AlwaysStoppedAnimation(MetrixColors.primary),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '${detail.completed} / ${detail.total} точек пройдено',
                  style: const TextStyle(fontSize: 12, color: MetrixColors.textMuted),
                ),
                if (detail.status == 'completed') ...[
                  const SizedBox(height: AppSpacing.sm),
                  const Row(
                    children: [
                      Icon(Icons.check_circle_rounded, size: 18, color: MetrixColors.accent),
                      SizedBox(width: 6),
                      Text('Обход завершён', style: TextStyle(color: MetrixColors.accent, fontWeight: FontWeight.w600, fontSize: 13)),
                    ],
                  ),
                ] else if (detail.isOverdue) ...[
                  const SizedBox(height: AppSpacing.sm),
                  const Row(
                    children: [
                      Icon(Icons.warning_amber_rounded, size: 18, color: MetrixColors.danger),
                      SizedBox(width: 6),
                      Text('Обход просрочен', style: TextStyle(color: MetrixColors.danger, fontWeight: FontWeight.w600, fontSize: 13)),
                    ],
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          for (final point in detail.points) ...[
            _PointRow(point: point, onTap: () => _openPoint(point)),
            const SizedBox(height: AppSpacing.sm),
          ],
        ],
      ),
    );
  }
}

class _PointRow extends StatelessWidget {
  final RoundRoutePoint point;
  final VoidCallback onTap;

  const _PointRow({required this.point, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: point.isVisited ? null : onTap,
      borderRadius: BorderRadius.circular(16),
      child: AppCard(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: point.isVisited ? MetrixColors.accent.withValues(alpha: 0.12) : MetrixColors.surfaceMuted,
                shape: BoxShape.circle,
              ),
              child: point.isVisited
                  ? const Icon(Icons.check_rounded, size: 18, color: MetrixColors.accent)
                  : Text('${point.order}', style: const TextStyle(fontWeight: FontWeight.w700, color: MetrixColors.textMuted)),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    point.pointName,
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14, color: MetrixColors.text),
                  ),
                  if (point.location.isNotEmpty)
                    Text(point.location, style: const TextStyle(fontSize: 12, color: MetrixColors.textMuted)),
                ],
              ),
            ),
            if (!point.isVisited) const Icon(Icons.qr_code_scanner_rounded, size: 20, color: MetrixColors.primary),
          ],
        ),
      ),
    );
  }
}
