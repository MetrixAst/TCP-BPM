import 'package:flutter/material.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/api_result.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../data/finances_repository.dart';
import '../data/finance_dto.dart';

class FinancesScreen extends StatefulWidget {
  const FinancesScreen({super.key});

  @override
  State<FinancesScreen> createState() => _FinancesScreenState();
}

class _FinancesScreenState extends State<FinancesScreen> {
  late final FinancesRepository _repository;

  bool _isLoading = true;
  String? _errorMessage;
  List<TenantPaymentDto> _payments = [];
  List<PaymentCalendarEntryDto> _calendar = [];
  int _tabIndex = 0;

  @override
  void initState() {
    super.initState();
    _repository = FinancesRepository(dio: DioClient().dio);
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final paymentsResult = await _repository.getPayments();
    final calendarResult = await _repository.getCalendar();

    if (!mounted) return;

    setState(() {
      _isLoading = false;

      switch (paymentsResult) {
        case Success(:final data):
          _payments = data;
        case Failure(:final message):
          _errorMessage = message;
      }

      switch (calendarResult) {
        case Success(:final data):
          _calendar = data;
        case Failure(:final message):
          _errorMessage ??= message;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: AppTopBar(
        title: 'Финансы',
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            onPressed: _load,
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null && _payments.isEmpty && _calendar.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                _errorMessage!.contains('доступа') ? Icons.lock_outline : Icons.error_outline,
                color: MetrixColors.danger,
                size: 40,
              ),
              const SizedBox(height: AppSpacing.sm),
              Text(_errorMessage!, style: const TextStyle(color: MetrixColors.danger), textAlign: TextAlign.center),
            ],
          ),
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          _SummaryCard(payments: _payments, calendar: _calendar),
          const SizedBox(height: AppSpacing.xl),
          _SegmentedTabs(
            index: _tabIndex,
            labels: const ['Платежи', 'Календарь'],
            counts: [_payments.length, _calendar.length],
            onChanged: (i) => setState(() => _tabIndex = i),
          ),
          const SizedBox(height: AppSpacing.md),
          if (_tabIndex == 0) ..._buildPaymentsList() else ..._buildCalendarList(),
        ],
      ),
    );
  }

  List<Widget> _buildPaymentsList() {
    if (_payments.isEmpty) {
      return const [_EmptyState(text: 'Платежей не найдено')];
    }
    return _payments.map((p) => Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: _PaymentCard(payment: p),
    )).toList();
  }

  List<Widget> _buildCalendarList() {
    if (_calendar.isEmpty) {
      return const [_EmptyState(text: 'Нет предстоящих платежей')];
    }
    return _calendar.map((e) => Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: _CalendarCard(entry: e),
    )).toList();
  }
}

/// Верхняя карточка со сводкой — тёмная, как акцентная плашка на логине/home,
/// чтобы финансовый раздел сразу считывался как "важные цифры".
class _SummaryCard extends StatelessWidget {
  final List<TenantPaymentDto> payments;
  final List<PaymentCalendarEntryDto> calendar;

  const _SummaryCard({required this.payments, required this.calendar});

  double _sumBalance() =>
      payments.fold<double>(0, (sum, p) => sum + (double.tryParse(p.balance) ?? 0));

  int _overdueCount() => payments.where((p) => p.overdueDays > 0).length;

  String _formatMoney(double value) {
    final rounded = value.round();
    final str = rounded.abs().toString();
    final buffer = StringBuffer();
    for (int i = 0; i < str.length; i++) {
      if (i > 0 && (str.length - i) % 3 == 0) buffer.write(' ');
      buffer.write(str[i]);
    }
    return '${rounded < 0 ? '-' : ''}${buffer.toString()} ₸';
  }

  @override
  Widget build(BuildContext context) {
    final balance = _sumBalance();
    final overdue = _overdueCount();

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
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Общая задолженность',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 12.5, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 6),
          Text(
            _formatMoney(balance),
            style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: AppSpacing.md),
          Container(height: 1, color: Colors.white.withValues(alpha: 0.1)),
          const SizedBox(height: AppSpacing.md),
          Row(
            children: [
              Expanded(
                child: _SummaryStat(
                  icon: Icons.warning_amber_rounded,
                  iconColor: const Color(0xFFFF8A65),
                  label: 'Просрочено',
                  value: '$overdue',
                ),
              ),
              Container(width: 1, height: 32, color: Colors.white.withValues(alpha: 0.1)),
              Expanded(
                child: _SummaryStat(
                  icon: Icons.event_outlined,
                  iconColor: const Color(0xFF7DD3A8),
                  label: 'В календаре',
                  value: '${calendar.length}',
                ),
              ),
              Container(width: 1, height: 32, color: Colors.white.withValues(alpha: 0.1)),
              Expanded(
                child: _SummaryStat(
                  icon: Icons.receipt_long_outlined,
                  iconColor: const Color(0xFF90B4FF),
                  label: 'Всего записей',
                  value: '${payments.length}',
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SummaryStat extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String label;
  final String value;

  const _SummaryStat({required this.icon, required this.iconColor, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 16, color: iconColor),
        const SizedBox(height: 6),
        Text(value, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w700)),
        const SizedBox(height: 2),
        Text(label, style: TextStyle(color: Colors.white.withValues(alpha: 0.55), fontSize: 10.5)),
      ],
    );
  }
}

/// Кастомный переключатель вкладок в духе остального приложения
/// (тот же паттерн, что "Мои/Все" на экране задач), с бейджем-счётчиком.
class _SegmentedTabs extends StatelessWidget {
  final int index;
  final List<String> labels;
  final List<int> counts;
  final ValueChanged<int> onChanged;

  const _SegmentedTabs({
    required this.index,
    required this.labels,
    required this.counts,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: MetrixColors.surfaceMuted,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: MetrixColors.border),
      ),
      child: Row(
        children: List.generate(labels.length, (i) {
          final active = i == index;
          return Expanded(
            child: InkWell(
              borderRadius: BorderRadius.circular(9),
              onTap: () => onChanged(i),
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 9),
                decoration: BoxDecoration(
                  color: active ? MetrixColors.surface : Colors.transparent,
                  borderRadius: BorderRadius.circular(9),
                  boxShadow: active
                      ? [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.06),
                      blurRadius: 4,
                      offset: const Offset(0, 1),
                    ),
                  ]
                      : null,
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      labels[i],
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: active ? MetrixColors.text : MetrixColors.textMuted,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                      decoration: BoxDecoration(
                        color: active ? MetrixColors.primary.withValues(alpha: 0.1) : MetrixColors.border,
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Text(
                        '${counts[i]}',
                        style: TextStyle(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w700,
                          color: active ? MetrixColors.primary : MetrixColors.textMuted,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
      ),
    );
  }
}

class _PaymentCard extends StatelessWidget {
  final TenantPaymentDto payment;

  const _PaymentCard({required this.payment});

  Color _statusColor(String status) {
    switch (status) {
      case 'paid':
        return MetrixColors.accent;
      case 'overdue':
        return MetrixColors.danger;
      case 'pending':
        return MetrixColors.warning;
      default:
        return MetrixColors.textMuted;
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = _statusColor(payment.status);

    return Container(
      decoration: BoxDecoration(
        color: MetrixColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: MetrixColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(width: 4, color: color),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            payment.tenantName,
                            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14.5),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: color.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            payment.statusDisplay,
                            style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${payment.contractNumber} · ${payment.period}',
                      style: const TextStyle(fontSize: 12, color: MetrixColors.textMuted),
                    ),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        _MoneyChip(label: 'Начислено', value: payment.charged),
                        const SizedBox(width: 8),
                        _MoneyChip(label: 'Оплачено', value: payment.paid, color: MetrixColors.accent),
                        const SizedBox(width: 8),
                        _MoneyChip(label: 'Баланс', value: payment.balance, color: color),
                      ],
                    ),
                    if (payment.overdueDays > 0) ...[
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          const Icon(Icons.schedule_rounded, size: 13, color: MetrixColors.danger),
                          const SizedBox(width: 4),
                          Text(
                            'Просрочка ${payment.overdueDays} дн.',
                            style: const TextStyle(fontSize: 11.5, color: MetrixColors.danger, fontWeight: FontWeight.w600),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MoneyChip extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;

  const _MoneyChip({required this.label, required this.value, this.color});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontSize: 10, color: MetrixColors.textMuted)),
          const SizedBox(height: 1),
          Text(
            value,
            style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: color ?? MetrixColors.text),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

class _CalendarCard extends StatelessWidget {
  final PaymentCalendarEntryDto entry;

  const _CalendarCard({required this.entry});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: MetrixColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: MetrixColors.border),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: MetrixColors.primary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(11),
            ),
            child: const Icon(Icons.event_available_outlined, color: MetrixColors.primary, size: 20),
          ),
          const SizedBox(width: AppSpacing.sm + 4),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(entry.tenantName, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                const SizedBox(height: 2),
                Text('Ожидается ${entry.expectedDate}', style: const TextStyle(fontSize: 12, color: MetrixColors.textMuted)),
              ],
            ),
          ),
          Text(
            entry.expectedAmount,
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: MetrixColors.text),
          ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final String text;

  const _EmptyState({required this.text});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 60),
      child: Center(
        child: Column(
          children: [
            Icon(Icons.inbox_outlined, size: 36, color: MetrixColors.textMuted.withValues(alpha: 0.5)),
            const SizedBox(height: 8),
            Text(text, style: const TextStyle(color: MetrixColors.textMuted, fontSize: 13)),
          ],
        ),
      ),
    );
  }
}