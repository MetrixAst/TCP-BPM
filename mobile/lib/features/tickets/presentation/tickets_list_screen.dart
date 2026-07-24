import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/api_result.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../data/tickets_repository.dart';
import '../data/ticket_dto.dart';
import '../data/ticket_enums.dart';

class TicketsListScreen extends StatefulWidget {
  const TicketsListScreen({super.key});

  @override
  State<TicketsListScreen> createState() => _TicketsListScreenState();
}

class _TicketsListScreenState extends State<TicketsListScreen> {
  late final TicketsRepository _repository;

  final List<TicketDto> _tickets = [];
  bool _isLoading = true;
  bool _isLoadingMore = false;
  String? _errorMessage;
  int _currentPage = 1;
  bool _hasMore = true;

  TicketStatus? _statusFilter;
  TicketCategory? _categoryFilter;

  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _repository = TicketsRepository(dio: DioClient().dio);
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

    final result = await _repository.getTickets(
      status: _statusFilter?.value,
      category: _categoryFilter?.value,
      page: 1,
    );

    if (!mounted) return;

    setState(() {
      _isLoading = false;
      switch (result) {
        case Success(:final data):
          _tickets
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

    final result = await _repository.getTickets(
      status: _statusFilter?.value,
      category: _categoryFilter?.value,
      page: _currentPage + 1,
    );

    if (!mounted) return;

    setState(() {
      _isLoadingMore = false;
      switch (result) {
        case Success(:final data):
          _tickets.addAll(data.results);
          _hasMore = data.next != null;
          _currentPage += 1;
        case Failure():
        // тихо игнорируем ошибку подгрузки, список уже частично показан
          _hasMore = false;
      }
    });
  }

  void _applyFilters({TicketStatus? status, TicketCategory? category}) {
    setState(() {
      _statusFilter = status;
      _categoryFilter = category;
    });
    _load(reset: true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: const AppTopBar(title: 'Заявки'),
      body: Column(
        children: [
          _FilterBar(
            selectedStatus: _statusFilter,
            selectedCategory: _categoryFilter,
            onChanged: _applyFilters,
          ),
          Expanded(child: _buildBody()),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: MetrixColors.primary,
        onPressed: () async {
          final created = await context.push<bool>('/tickets/create');
          if (created == true) {
            _load(reset: true);
          }
        },
        child: const Icon(Icons.add, color: Colors.white),
      ),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null && _tickets.isEmpty) {
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

    if (_tickets.isEmpty) {
      return const Center(
        child: Text('Заявок не найдено', style: TextStyle(color: MetrixColors.textMuted)),
      );
    }

    return RefreshIndicator(
      onRefresh: () => _load(reset: true),
      child: ListView.separated(
        controller: _scrollController,
        padding: const EdgeInsets.all(AppSpacing.lg),
        itemCount: _tickets.length + (_hasMore ? 1 : 0),
        separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
        itemBuilder: (context, index) {
          if (index >= _tickets.length) {
            return const Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.md),
              child: Center(child: CircularProgressIndicator()),
            );
          }
          final ticket = _tickets[index];
          return _TicketCard(
            ticket: ticket,
            onTap: () => context.push('/tickets/${ticket.id}'),
          );
        },
      ),
    );
  }
}

class _FilterBar extends StatelessWidget {
  final TicketStatus? selectedStatus;
  final TicketCategory? selectedCategory;
  final void Function({TicketStatus? status, TicketCategory? category}) onChanged;

  const _FilterBar({
    required this.selectedStatus,
    required this.selectedCategory,
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
      child: Row(
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
              label: 'Категория',
              value: selectedCategory?.label,
              onTap: () => _showCategoryPicker(context),
            ),
          ),
        ],
      ),
    );
  }

  void _showStatusPicker(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => _PickerSheet<TicketStatus>(
        title: 'Статус',
        options: TicketStatus.values,
        selected: selectedStatus,
        labelOf: (s) => s.label,
        onSelect: (status) {
          Navigator.pop(context);
          onChanged(status: status, category: selectedCategory);
        },
      ),
    );
  }

  void _showCategoryPicker(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => _PickerSheet<TicketCategory>(
        title: 'Категория',
        options: TicketCategory.values,
        selected: selectedCategory,
        labelOf: (c) => c.label,
        onSelect: (category) {
          Navigator.pop(context);
          onChanged(status: selectedStatus, category: category);
        },
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
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.7,
        ),
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

class _TicketCard extends StatelessWidget {
  final TicketDto ticket;
  final VoidCallback onTap;

  const _TicketCard({required this.ticket, required this.onTap});

  Color _statusColor(String status) {
    switch (status) {
      case 'new':
        return MetrixColors.warning;
      case 'accepted':
      case 'in_progress':
        return MetrixColors.primary;
      case 'done':
        return MetrixColors.accent;
      case 'rejected':
      case 'cancelled':
        return MetrixColors.danger;
      default:
        return MetrixColors.textMuted;
    }
  }

  @override
  Widget build(BuildContext context) {
    final statusLabel = TicketStatus.fromValue(ticket.status).label;
    final categoryLabel = TicketCategory.fromValue(ticket.category).label;
    final color = _statusColor(ticket.status);

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
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (ticket.photo != null)
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: Image.network(
                  ticket.photo!,
                  width: 52,
                  height: 52,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => _fallbackThumb(),
                ),
              )
            else
              _fallbackThumb(),
            const SizedBox(width: AppSpacing.sm + 4),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          '${ticket.number} · $categoryLabel',
                          style: const TextStyle(fontSize: 11, color: MetrixColors.textMuted),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    ticket.title,
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 8),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        statusLabel,
                        style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _fallbackThumb() {
    return Container(
      width: 52,
      height: 52,
      decoration: BoxDecoration(
        color: MetrixColors.surfaceMuted,
        borderRadius: BorderRadius.circular(10),
      ),
      child: const Icon(Icons.description_outlined, color: MetrixColors.textMuted, size: 22),
    );
  }
}