import 'package:flutter/material.dart';

import '../../../core/network/api_result.dart';
import '../../../core/network/dio_client.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../data/round_point_report.dart';
import '../data/rounds_repository.dart';

/// Отчёт по помещению: руководитель или админ сканирует QR и видит, кто и
/// когда проверял его по каждому чек-листу, что просрочено и какие
/// неисправности не устранены.
class RoundPointReportScreen extends StatefulWidget {
  final String pointUuid;
  final String pointName;
  final RoundsRepository? repository;

  const RoundPointReportScreen({
    super.key,
    required this.pointUuid,
    required this.pointName,
    this.repository,
  });

  @override
  State<RoundPointReportScreen> createState() => _RoundPointReportScreenState();
}

class _RoundPointReportScreenState extends State<RoundPointReportScreen> {
  late final RoundsRepository _repository = widget.repository ?? RoundsRepository(dio: DioClient().dio);
  ApiResult<RoundPointReport>? _result;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _result = null);
    final result = await _repository.getPointReport(widget.pointUuid);
    if (mounted) setState(() => _result = result);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: AppTopBar(title: widget.pointName),
      body: switch (_result) {
        null => const Center(child: CircularProgressIndicator()),
        Failure(:final message) => _Message(text: message, onRetry: _load),
        Success(:final data) => RefreshIndicator(onRefresh: _load, child: _ReportBody(report: data)),
      },
    );
  }
}

class _ReportBody extends StatelessWidget {
  final RoundPointReport report;

  const _ReportBody({required this.report});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        if (report.location.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.md),
            child: Text(report.location, style: const TextStyle(color: MetrixColors.textMuted, fontSize: 13)),
          ),
        const _SectionTitle('Проверки по чек-листам'),
        for (final row in report.checklists) ...[
          _ChecklistCard(row: row),
          const SizedBox(height: AppSpacing.sm),
        ],
        const SizedBox(height: AppSpacing.md),
        _SectionTitle('Открытые неисправности: ${report.openDefects.length}'),
        if (report.openDefects.isEmpty)
          const _Muted('Неисправностей нет')
        else
          for (final defect in report.openDefects) ...[
            AppCard(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(defect.description, style: const TextStyle(fontWeight: FontWeight.w600, color: MetrixColors.danger)),
                  if (defect.checklistName != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      defect.checklistName!,
                      style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: MetrixColors.text),
                    ),
                  ],
                  const SizedBox(height: 4),
                  _Muted([
                    if (defect.createdAt != null) _formatDateTime(defect.createdAt!),
                    if (defect.reportedBy != null) defect.reportedBy!,
                  ].join(' · ')),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
          ],
        const SizedBox(height: AppSpacing.md),
        const _SectionTitle('Последние посещения'),
        if (report.recentVisits.isEmpty)
          const _Muted('Посещений ещё не было')
        else
          for (final visit in report.recentVisits) ...[
            AppCard(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${visit.createdAt != null ? _formatDateTime(visit.createdAt!) : ''} · ${visit.employeeName}',
                    style: const TextStyle(fontWeight: FontWeight.w600, color: MetrixColors.text),
                  ),
                  if (visit.checklistName != null) _Muted(visit.checklistName!),
                  const SizedBox(height: 4),
                  Text(
                    visit.failedCount == 0 ? 'Всё в порядке' : 'Несоответствий: ${visit.failedCount}',
                    style: TextStyle(
                      fontSize: 13,
                      color: visit.failedCount == 0 ? MetrixColors.accent : MetrixColors.danger,
                    ),
                  ),
                  if (visit.comment.isNotEmpty) _Muted(visit.comment),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
          ],
      ],
    );
  }
}

class _ChecklistCard extends StatelessWidget {
  final RoundReportChecklist row;

  const _ChecklistCard({required this.row});

  @override
  Widget build(BuildContext context) {
    final statusColor = row.isOverdue ? MetrixColors.danger : MetrixColors.accent;
    final lastVisit = row.lastVisitAt == null
        ? 'Ещё не проверяли'
        : 'Последняя проверка: ${_formatDateTime(row.lastVisitAt!)}${row.lastVisitBy != null ? ', ${row.lastVisitBy}' : ''}';
    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  row.checklistName ?? 'Без чек-листа',
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: MetrixColors.text),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  row.isOverdue ? 'Просрочено' : 'В графике',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: statusColor),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          _Muted('${row.assignee} · каждые ${row.intervalHours} ч'),
          const SizedBox(height: 2),
          _Muted(lastVisit),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String text;

  const _SectionTitle(this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Text(text, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: MetrixColors.text)),
    );
  }
}

class _Muted extends StatelessWidget {
  final String text;

  const _Muted(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(text, style: const TextStyle(fontSize: 13, color: MetrixColors.textMuted));
  }
}

class _Message extends StatelessWidget {
  final String text;
  final VoidCallback onRetry;

  const _Message({required this.text, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline_rounded, size: 44, color: MetrixColors.danger),
            const SizedBox(height: AppSpacing.sm),
            Text(text, textAlign: TextAlign.center, style: const TextStyle(fontSize: 15, color: MetrixColors.text)),
            const SizedBox(height: AppSpacing.md),
            OutlinedButton(onPressed: onRetry, child: const Text('Повторить')),
          ],
        ),
      ),
    );
  }
}

String _formatDateTime(DateTime value) {
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(value.day)}.${two(value.month)}.${value.year} ${two(value.hour)}:${two(value.minute)}';
}
