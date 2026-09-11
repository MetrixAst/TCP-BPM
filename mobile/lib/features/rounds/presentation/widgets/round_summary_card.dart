import 'package:flutter/material.dart';

import '../../../../core/theme/metrix_colors.dart';
import '../../../../shared/spacing.dart';
import '../../../../shared/widgets/app_card.dart';
import '../../data/planned_round_summary.dart';

String _twoDigits(int n) => n.toString().padLeft(2, '0');

String formatTimeRange(DateTime start, DateTime end) {
  return '${_twoDigits(start.hour)}:${_twoDigits(start.minute)} — ${_twoDigits(end.hour)}:${_twoDigits(end.minute)}';
}

class _StatusInfo {
  final String label;
  final Color color;
  const _StatusInfo(this.label, this.color);
}

_StatusInfo _statusInfo(PlannedRoundSummary round) {
  if (round.isOverdue) return const _StatusInfo('Просрочен', MetrixColors.danger);
  switch (round.status) {
    case 'completed':
      return const _StatusInfo('Завершён', MetrixColors.accent);
    case 'missed':
      return const _StatusInfo('Пропущен', MetrixColors.danger);
    case 'in_progress':
      return const _StatusInfo('В процессе', MetrixColors.warning);
    default:
      return const _StatusInfo('Ожидает', MetrixColors.textMuted);
  }
}

class RoundSummaryCard extends StatelessWidget {
  final PlannedRoundSummary round;
  final VoidCallback? onTap;

  const RoundSummaryCard({super.key, required this.round, this.onTap});

  @override
  Widget build(BuildContext context) {
    final status = _statusInfo(round);
    final progress = round.totalPoints == 0 ? 0.0 : round.completedPoints / round.totalPoints;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: AppCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    round.routeName,
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: MetrixColors.text),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: status.color.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    status.label,
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: status.color),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              formatTimeRange(round.plannedStart, round.plannedEnd),
              style: const TextStyle(fontSize: 12, color: MetrixColors.textMuted),
            ),
            const SizedBox(height: AppSpacing.sm),
            ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: LinearProgressIndicator(
                value: progress,
                minHeight: 6,
                backgroundColor: MetrixColors.surfaceMuted,
                valueColor: const AlwaysStoppedAnimation(MetrixColors.primary),
              ),
            ),
            const SizedBox(height: 4),
            Text(
              '${round.completedPoints} / ${round.totalPoints} точек',
              style: const TextStyle(fontSize: 12, color: MetrixColors.textMuted),
            ),
          ],
        ),
      ),
    );
  }
}
