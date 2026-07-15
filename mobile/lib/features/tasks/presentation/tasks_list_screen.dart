import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/api_result.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../profile/data/profile_repository.dart';
import '../data/tasks_repository.dart';
import '../data/task_dto.dart';
import '../data/task_enums.dart';
import '../data/task_status_color.dart';

class TasksListScreen extends StatefulWidget {
  const TasksListScreen({super.key});

  @override
  State<TasksListScreen> createState() => _TasksListScreenState();
}

class _TasksListScreenState extends State<TasksListScreen> {
  late final TasksRepository _repository;
  late final ProfileRepository _profileRepository;

  final List<TaskDto> _tasks = [];
  bool _isLoading = true;
  bool _isLoadingMore = false;
  String? _errorMessage;
  int _currentPage = 1;
  bool _hasMore = true;
  int? _myUserId;

  TaskStatus? _statusFilter;
  TaskPriority? _priorityFilter;
  bool _onlyMine = true;

  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    final dio = DioClient().dio;
    _repository = TasksRepository(dio: dio);
    _profileRepository = ProfileRepository(dio: dio);
    _scrollController.addListener(_onScroll);
    _init();
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _init() async {
    final profileResult = await _profileRepository.getProfile();
    if (!mounted) return;

    switch (profileResult) {
      case Success(:final data):
        _myUserId = data.id;
      case Failure():
        break; // не блокируем, просто не будет фильтра "мои"
    }

    _load(reset: true);
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

    final result = await _repository.getTasks(
      executorId: _onlyMine ? _myUserId : null,
      status: _statusFilter?.value,
      priority: _priorityFilter?.value,
      page: 1,
    );

    if (!mounted) return;

    setState(() {
      _isLoading = false;
      switch (result) {
        case Success(:final data):
          _tasks
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

    final result = await _repository.getTasks(
      executorId: _onlyMine ? _myUserId : null,
      status: _statusFilter?.value,
      priority: _priorityFilter?.value,
      page: _currentPage + 1,
    );

    if (!mounted) return;

    setState(() {
      _isLoadingMore = false;
      switch (result) {
        case Success(:final data):
          _tasks.addAll(data.results);
          _hasMore = data.next != null;
          _currentPage += 1;
        case Failure():
          _hasMore = false;
      }
    });
  }

  void _toggleOnlyMine(bool value) {
    setState(() => _onlyMine = value);
    _load(reset: true);
  }

  void _applyFilters({TaskStatus? status, TaskPriority? priority}) {
    setState(() {
      _statusFilter = status;
      _priorityFilter = priority;
    });
    _load(reset: true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: const AppTopBar(title: 'Мои задачи'),
      body: Column(
        children: [
          _FilterBar(
            onlyMine: _onlyMine,
            selectedStatus: _statusFilter,
            selectedPriority: _priorityFilter,
            onToggleOnlyMine: _toggleOnlyMine,
            onChanged: _applyFilters,
          ),
          Expanded(child: _buildBody()),
        ],
      ),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null && _tasks.isEmpty) {
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

    if (_tasks.isEmpty) {
      return const Center(
        child: Text('Задач не найдено', style: TextStyle(color: MetrixColors.textMuted)),
      );
    }

    return RefreshIndicator(
      onRefresh: () => _load(reset: true),
      child: ListView.separated(
        controller: _scrollController,
        padding: const EdgeInsets.all(AppSpacing.lg),
        itemCount: _tasks.length + (_hasMore ? 1 : 0),
        separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
        itemBuilder: (context, index) {
          if (index >= _tasks.length) {
            return const Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.md),
              child: Center(child: CircularProgressIndicator()),
            );
          }
          final task = _tasks[index];
          return _TaskCard(
            task: task,
            onTap: () => context.push('/tasks/${task.id}'),
          );
        },
      ),
    );
  }
}

class _FilterBar extends StatelessWidget {
  final bool onlyMine;
  final TaskStatus? selectedStatus;
  final TaskPriority? selectedPriority;
  final void Function(bool) onToggleOnlyMine;
  final void Function({TaskStatus? status, TaskPriority? priority}) onChanged;

  const _FilterBar({
    required this.onlyMine,
    required this.selectedStatus,
    required this.selectedPriority,
    required this.onToggleOnlyMine,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
      decoration: const BoxDecoration(
        color: MetrixColors.surface,
        border: Border(bottom: BorderSide(color: MetrixColors.border)),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: _ToggleChip(
                  label: 'Мои',
                  active: onlyMine,
                  onTap: () => onToggleOnlyMine(true),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: _ToggleChip(
                  label: 'Все',
                  active: !onlyMine,
                  onTap: () => onToggleOnlyMine(false),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              Expanded(
                child: _FilterChip(
                  label: 'Статус',
                  value: selectedStatus?.label,
                  onTap: () => _showStatusPicker(context),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: _FilterChip(
                  label: 'Приоритет',
                  value: selectedPriority?.label,
                  onTap: () => _showPriorityPicker(context),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _showStatusPicker(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => _PickerSheet<TaskStatus>(
        title: 'Статус',
        options: TaskStatus.values,
        selected: selectedStatus,
        labelOf: (s) => s.label,
        onSelect: (status) {
          Navigator.pop(context);
          onChanged(status: status, priority: selectedPriority);
        },
      ),
    );
  }

  void _showPriorityPicker(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => _PickerSheet<TaskPriority>(
        title: 'Приоритет',
        options: TaskPriority.values,
        selected: selectedPriority,
        labelOf: (p) => p.label,
        onSelect: (priority) {
          Navigator.pop(context);
          onChanged(status: selectedStatus, priority: priority);
        },
      ),
    );
  }
}

class _ToggleChip extends StatelessWidget {
  final String label;
  final bool active;
  final VoidCallback onTap;

  const _ToggleChip({required this.label, required this.active, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 8),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: active ? MetrixColors.primary : MetrixColors.surfaceMuted,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: active ? Colors.white : MetrixColors.textMuted,
          ),
        ),
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final String? value;
  final VoidCallback onTap;

  const _FilterChip({required this.label, required this.value, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final active = value != null;
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: active ? MetrixColors.primary.withValues(alpha: 0.08) : MetrixColors.surfaceMuted,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: active ? MetrixColors.primary : MetrixColors.border),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                value ?? label,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: active ? MetrixColors.primary : MetrixColors.textMuted,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(width: 4),
            Icon(Icons.keyboard_arrow_down_rounded, size: 18, color: active ? MetrixColors.primary : MetrixColors.textMuted),
          ],
        ),
      ),
    );
  }
}

class _PickerSheet<T> extends StatelessWidget {
  final String title;
  final List<T> options;
  final T? selected;
  final String Function(T) labelOf;
  final void Function(T?) onSelect;

  const _PickerSheet({
    required this.title,
    required this.options,
    required this.selected,
    required this.labelOf,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.7),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            ),
            Flexible(
              child: ListView(
                shrinkWrap: true,
                children: [
                  ListTile(
                    title: const Text('Все'),
                    trailing: selected == null ? const Icon(Icons.check, color: MetrixColors.primary) : null,
                    onTap: () => onSelect(null),
                  ),
                  ...options.map((option) => ListTile(
                        title: Text(labelOf(option)),
                        trailing: selected == option ? const Icon(Icons.check, color: MetrixColors.primary) : null,
                        onTap: () => onSelect(option),
                      )),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TaskCard extends StatelessWidget {
  final TaskDto task;
  final VoidCallback onTap;

  const _TaskCard({required this.task, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final color = taskStatusColor(task.statusColor);

    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: MetrixColors.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: MetrixColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    task.title,
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    task.statusDisplay,
                    style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                const Icon(Icons.flag_outlined, size: 14, color: MetrixColors.textMuted),
                const SizedBox(width: 4),
                Text(task.priorityDisplay, style: const TextStyle(fontSize: 12, color: MetrixColors.textMuted)),
                if (task.deadline != null) ...[
                  const SizedBox(width: 12),
                  const Icon(Icons.event_outlined, size: 14, color: MetrixColors.textMuted),
                  const SizedBox(width: 4),
                  Text(task.deadline!, style: const TextStyle(fontSize: 12, color: MetrixColors.textMuted)),
                ],
                const Spacer(),
                if (task.executor != null)
                  Text(
                    task.executor!.name,
                    style: const TextStyle(fontSize: 11.5, color: MetrixColors.textMuted, fontWeight: FontWeight.w600),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}