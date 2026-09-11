import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/api_result.dart';
import '../../../core/network/dio_client.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../data/planned_round_summary.dart';
import '../data/rounds_repository.dart';
import 'widgets/round_summary_card.dart';

class RoundsTodayScreen extends StatefulWidget {
  const RoundsTodayScreen({super.key});

  @override
  State<RoundsTodayScreen> createState() => _RoundsTodayScreenState();
}

class _RoundsTodayScreenState extends State<RoundsTodayScreen> {
  late final RoundsRepository _repository;
  bool _isLoading = true;
  String? _error;
  List<PlannedRoundSummary> _rounds = const [];

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
    final result = await _repository.getToday();
    if (!mounted) return;
    setState(() {
      _isLoading = false;
      switch (result) {
        case Success(:final data):
          _rounds = data;
        case Failure(:final message):
          _error = message;
      }
    });
  }

  Future<void> _openRoute(PlannedRoundSummary round) async {
    await context.push('/rounds/route/${round.id}');
    if (!mounted) return;
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: AppTopBar(
        title: 'Обходы на сегодня',
        actions: [
          IconButton(
            icon: const Icon(Icons.history_rounded),
            tooltip: 'История',
            onPressed: () => context.push('/rounds/history'),
          ),
        ],
      ),
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
    if (_error != null) {
      return _ErrorState(message: _error!, onRetry: _load);
    }
    if (_rounds.isEmpty) {
      return ListView(
        children: const [
          SizedBox(height: 120),
          Icon(Icons.event_available_rounded, size: 44, color: MetrixColors.textMuted),
          SizedBox(height: AppSpacing.sm),
          Text('Нет заданий на сегодня', style: TextStyle(color: MetrixColors.textMuted, fontSize: 14), textAlign: TextAlign.center),
        ],
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.all(AppSpacing.lg),
      itemCount: _rounds.length,
      separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
      itemBuilder: (context, index) {
        final round = _rounds[index];
        return RoundSummaryCard(round: round, onTap: () => _openRoute(round));
      },
    );
  }
}

class _ErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _ErrorState({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline_rounded, size: 40, color: MetrixColors.danger),
            const SizedBox(height: AppSpacing.sm),
            Text(message, style: const TextStyle(color: MetrixColors.danger), textAlign: TextAlign.center),
            const SizedBox(height: AppSpacing.sm),
            TextButton(onPressed: onRetry, child: const Text('Повторить')),
          ],
        ),
      ),
    );
  }
}
