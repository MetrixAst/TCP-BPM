import 'package:flutter/material.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/api_result.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../data/tasks_repository.dart';
import '../data/task_dto.dart';
import '../data/task_action_dto.dart';
import '../data/task_status_color.dart';
import '../data/task_history_dto.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import '../../../core/database/app_database.dart';
import '../../../core/database/outbox_repository.dart';

class TaskDetailScreen extends StatefulWidget {
  final int taskId;

  const TaskDetailScreen({super.key, required this.taskId});

  @override
  State<TaskDetailScreen> createState() => _TaskDetailScreenState();
}

class _TaskDetailScreenState extends State<TaskDetailScreen> {
  late final TasksRepository _repository;
  late final OutboxRepository _outboxRepo;

  bool _isLoading = true;
  bool _isPerformingAction = false;
  bool _isDeleting = false;
  String? _errorMessage;
  TaskDto? _task;

  @override
  void initState() {
    super.initState();
    _repository = TasksRepository(dio: DioClient().dio);
    _load();
    _outboxRepo = OutboxRepository(db: AppDatabase.instance);
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final result = await _repository.getTask(widget.taskId);

    if (!mounted) return;

    setState(() {
      _isLoading = false;
      switch (result) {
        case Success(:final data):
          _task = data;
        case Failure(:final message):
          _errorMessage = message;
      }
    });
  }

  Future<void> _handleAction(TaskActionDto taskAction) async {
    setState(() => _isPerformingAction = true);

    final connectivity = await Connectivity().checkConnectivity();
    final isOffline = connectivity.every((r) => r == ConnectivityResult.none);

    if (isOffline) {
      await _outboxRepo.enqueue(
        type: OutboxOperationType.taskTransition,
        payload: {
          'task_id': widget.taskId,
          'action': taskAction.action,
        },
      );

      if (!mounted) return;
      setState(() => _isPerformingAction = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Нет сети — действие будет выполнено позже')),
      );
      return;
    }

    final result = await _repository.transition(widget.taskId, taskAction.action);

    if (!mounted) return;

    setState(() => _isPerformingAction = false);

    switch (result) {
      case Success(:final data):
        setState(() => _task = data);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Статус обновлён: ${data.statusDisplay}')),
        );
      case Failure(:final message):
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(message)),
        );
    }
  }

  Future<void> _handleDelete() async {
    final reasonController = TextEditingController();
    final reason = await showDialog<String>(
      context: context,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (dialogContext, setDialogState) {
            final trimmed = reasonController.text.trim();
            return AlertDialog(
              title: const Text('Удалить задачу?'),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Укажите причину удаления (не менее 5 символов).'),
                  const SizedBox(height: AppSpacing.sm),
                  TextField(
                    controller: reasonController,
                    autofocus: true,
                    maxLines: 3,
                    decoration: const InputDecoration(
                      hintText: 'Причина удаления',
                      border: OutlineInputBorder(),
                    ),
                    onChanged: (_) => setDialogState(() {}),
                  ),
                ],
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(dialogContext).pop(),
                  child: const Text('Отмена'),
                ),
                TextButton(
                  onPressed: trimmed.length < 5
                      ? null
                      : () => Navigator.of(dialogContext).pop(trimmed),
                  style: TextButton.styleFrom(foregroundColor: MetrixColors.danger),
                  child: const Text('Удалить'),
                ),
              ],
            );
          },
        );
      },
    );

    if (reason == null || !mounted) return;

    setState(() => _isDeleting = true);

    final result = await _repository.deleteTask(widget.taskId, reason: reason);

    if (!mounted) return;

    setState(() => _isDeleting = false);

    switch (result) {
      case Success():
        Navigator.of(context).pop(true);
      case Failure(:final message):
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(message)),
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: AppTopBar(
        title: _task != null ? 'Задача #${_task!.id}' : 'Задача',
        actions: (_task?.canDelete ?? false)
            ? [
                IconButton(
                  icon: _isDeleting
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.delete_outline, color: MetrixColors.danger),
                  onPressed: _isDeleting ? null : _handleDelete,
                ),
              ]
            : null,
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null || _task == null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: MetrixColors.danger, size: 40),
              const SizedBox(height: AppSpacing.sm),
              Text(_errorMessage ?? 'Не удалось загрузить задачу', style: const TextStyle(color: MetrixColors.danger), textAlign: TextAlign.center),
              const SizedBox(height: AppSpacing.md),
              ElevatedButton(onPressed: _load, child: const Text('Повторить')),
            ],
          ),
        ),
      );
    }

    final task = _task!;
    final statusColor = taskStatusColor(task.statusColor);

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        task.title,
                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17),
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: statusColor.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        task.statusDisplay,
                        style: TextStyle(fontSize: 11, color: statusColor, fontWeight: FontWeight.w600),
                      ),
                    ),
                  ],
                ),
                if (task.text.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Text(task.text, style: const TextStyle(fontSize: 14, color: MetrixColors.text)),
                ],
                const SizedBox(height: AppSpacing.md),
                Wrap(
                  spacing: 16,
                  runSpacing: 8,
                  children: [
                    _InfoChip(icon: Icons.flag_outlined, label: task.priorityDisplay),
                    if (task.deadline != null)
                      _InfoChip(icon: Icons.event_outlined, label: task.deadline!),
                    _InfoChip(icon: Icons.person_outline, label: 'Автор: ${task.author.name}'),
                    if (task.executor != null)
                      _InfoChip(icon: Icons.assignment_ind_outlined, label: 'Исполнитель: ${task.executor!.name}'),
                  ],
                ),
              ],
            ),
          ),
          if (task.availableActions.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.lg),
            const Text('Действия', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            const SizedBox(height: AppSpacing.sm),
       Wrap(
              spacing: 8,
              runSpacing: 8,
              children: task.availableActions.map((action) {
                final isOutline = action.color == 'outline-dark';
                final color = taskActionColor(action.color);
                return Material(
                  color: isOutline ? Colors.transparent : color,
                  borderRadius: BorderRadius.circular(10),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(10),
                    onTap: _isPerformingAction ? null : () => _handleAction(action),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(10),
                        border: isOutline ? Border.all(color: MetrixColors.border) : null,
                      ),
                      child: Text(
                        action.title,
                        style: TextStyle(
                          fontWeight: FontWeight.w600,
                          fontSize: 13.5,
                          color: isOutline ? MetrixColors.textMuted : Colors.white,
                        ),
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
          ],
          if (task.history.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.lg),
            const Text('История', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            const SizedBox(height: AppSpacing.sm),
            AppCard(
              child: Column(
                children: [
                  for (int i = 0; i < task.history.length; i++) ...[
                    if (i > 0) const Divider(height: 20, color: MetrixColors.border),
                    _TaskHistoryRow(entry: task.history[i]),
                  ],
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _TaskHistoryRow extends StatelessWidget {
  final TaskHistoryEntryDto entry;

  const _TaskHistoryRow({required this.entry});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 8,
          height: 8,
          margin: const EdgeInsets.only(top: 5),
          decoration: const BoxDecoration(
            color: MetrixColors.primary,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(entry.statusDisplay, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13.5)),
              const SizedBox(height: 2),
              Text(
                '${entry.user ?? 'Система'} · ${entry.date}',
                style: const TextStyle(fontSize: 11, color: MetrixColors.textMuted),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _InfoChip extends StatelessWidget {
  final IconData icon;
  final String label;

  const _InfoChip({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 15, color: MetrixColors.textMuted),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 12.5, color: MetrixColors.textMuted)),
      ],
    );
  }
}