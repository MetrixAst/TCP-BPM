import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/api_result.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../profile/data/profile_repository.dart';
import '../data/ticket_detail_repository.dart';
import '../data/ticket_detail_dto.dart';
import '../data/ticket_message_dto.dart';
import '../data/ticket_enums.dart';

class TicketDetailScreen extends StatefulWidget {
  final int ticketId;

  const TicketDetailScreen({super.key, required this.ticketId});

  @override
  State<TicketDetailScreen> createState() => _TicketDetailScreenState();
}

class _TicketDetailScreenState extends State<TicketDetailScreen> {
  late final TicketDetailRepository _repository;
  final TextEditingController _messageController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  int? _myUserId;
  bool _isLoading = true;
  String? _errorMessage;
  TicketDetailDto? _ticket;
  List<TicketMessageDto> _messages = [];
  bool _isSending = false;

  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _repository = TicketDetailRepository(dio: DioClient().dio);
    _loadMyUserId();
    _load();
    _pollTimer = Timer.periodic(const Duration(seconds: 10), (_) => _refreshMessages());
  }

  Future<void> _loadMyUserId() async {
    final profileRepo = ProfileRepository(dio: DioClient().dio);
    final result = await profileRepo.getProfile();
    if (!mounted) return;
    if (result is Success) {
      setState(() => _myUserId = (result as Success).data.id);
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final ticketResult = await _repository.getTicket(widget.ticketId);
    final messagesResult = await _repository.getMessages(widget.ticketId);

    if (!mounted) return;

    setState(() {
      _isLoading = false;
      switch (ticketResult) {
        case Success(:final data):
          _ticket = data;
        case Failure(:final message):
          _errorMessage = message;
      }
      switch (messagesResult) {
        case Success(:final data):
          _messages = data;
        case Failure():
          break;
      }
    });

    _scrollToBottom();
  }

  Future<void> _refreshMessages() async {
    if (!mounted) return;
    final result = await _repository.getMessages(widget.ticketId);
    if (!mounted) return;

    switch (result) {
      case Success(:final data):
        if (data.length != _messages.length) {
          setState(() => _messages = data);
          _scrollToBottom();
        }
      case Failure():
        break;
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _handleSend() async {
    final text = _messageController.text.trim();
    if (text.isEmpty) return;

    setState(() => _isSending = true);
    final result = await _repository.sendMessage(widget.ticketId, text);

    if (!mounted) return;
    setState(() => _isSending = false);

    switch (result) {
      case Success(:final data):
        setState(() {
          _messages = [..._messages, data];
          _messageController.clear();
        });
        _scrollToBottom();
      case Failure(:final message):
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(message)),
        );
    }
  }

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
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: AppTopBar(title: _ticket?.number ?? 'Заявка'),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null || _ticket == null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: MetrixColors.danger, size: 40),
              const SizedBox(height: AppSpacing.sm),
              Text(_errorMessage ?? 'Не удалось загрузить заявку', style: const TextStyle(color: MetrixColors.danger), textAlign: TextAlign.center),
            ],
          ),
        ),
      );
    }

    final ticket = _ticket!;

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          _TicketInfoCard(ticket: ticket, statusColor: _statusColor(ticket.status)),
          const SizedBox(height: AppSpacing.lg),
          const Text('Чат', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
          const SizedBox(height: AppSpacing.sm),
          Container(
            decoration: BoxDecoration(
              color: MetrixColors.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: MetrixColors.border),
            ),
            clipBehavior: Clip.antiAlias,
            child: Column(
              children: [
                SizedBox(
                  height: 320,
                  child: _messages.isEmpty
                      ? const Center(
                          child: Text('Сообщений пока нет', style: TextStyle(color: MetrixColors.textMuted, fontSize: 13)),
                        )
                      : ListView(
                          controller: _scrollController,
                          padding: const EdgeInsets.all(AppSpacing.md),
                          children: _messages
                              .map((m) => _MessageBubble(
                                    message: m,
                                    isMine: m.author?.id == _myUserId,
                                  ))
                              .toList(),
                        ),
                ),
                const Divider(height: 1, color: MetrixColors.border),
                _MessageInput(
                  controller: _messageController,
                  isSending: _isSending,
                  onSend: _handleSend,
                ),
              ],
            ),
          ),
          if (ticket.history.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.lg),
            const Text('История статусов', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            const SizedBox(height: AppSpacing.sm),
            AppCard(
              child: Column(
                children: [
                  for (int i = 0; i < ticket.history.length; i++) ...[
                    if (i > 0) const Divider(height: 20, color: MetrixColors.border),
                    _HistoryRow(entry: ticket.history[i]),
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

class _TicketInfoCard extends StatelessWidget {
  final TicketDetailDto ticket;
  final Color statusColor;

  const _TicketInfoCard({required this.ticket, required this.statusColor});

  @override
  Widget build(BuildContext context) {
    final categoryLabel = TicketCategory.fromValue(ticket.category).label;
    final priorityLabel = TicketPriority.fromValue(ticket.priority).label;
    final statusLabel = TicketStatus.fromValue(ticket.status).label;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  ticket.title,
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
                  statusLabel,
                  style: TextStyle(fontSize: 11, color: statusColor, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(ticket.description, style: const TextStyle(fontSize: 14, color: MetrixColors.text)),
          const SizedBox(height: AppSpacing.md),
          if (ticket.photo != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: Image.network(ticket.photo!, height: 160, width: double.infinity, fit: BoxFit.cover),
            ),
            const SizedBox(height: AppSpacing.sm),
          ],
          Wrap(
            spacing: 16,
            runSpacing: 8,
            children: [
              _InfoChip(icon: Icons.category_outlined, label: categoryLabel),
              _InfoChip(icon: Icons.flag_outlined, label: priorityLabel),
              if (ticket.room.isNotEmpty) _InfoChip(icon: Icons.room_outlined, label: ticket.room),
            ],
          ),
        ],
      ),
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

class _MessageBubble extends StatelessWidget {
  final TicketMessageDto message;
  final bool isMine;

  const _MessageBubble({required this.message, required this.isMine});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Column(
        crossAxisAlignment: isMine ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          if (!isMine)
            Padding(
              padding: const EdgeInsets.only(bottom: 3, left: 4),
              child: Text(
                message.author?.fullName ?? 'Система',
                style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w600, color: MetrixColors.textMuted),
              ),
            ),
          Container(
            constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.6),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: isMine ? MetrixColors.primary : MetrixColors.surfaceMuted,
              borderRadius: BorderRadius.only(
                topLeft: const Radius.circular(14),
                topRight: const Radius.circular(14),
                bottomLeft: Radius.circular(isMine ? 14 : 4),
                bottomRight: Radius.circular(isMine ? 4 : 14),
              ),
            ),
            child: Text(
              message.text,
              style: TextStyle(fontSize: 14, color: isMine ? Colors.white : MetrixColors.text),
            ),
          ),
        ],
      ),
    );
  }
}

class _MessageInput extends StatelessWidget {
  final TextEditingController controller;
  final bool isSending;
  final VoidCallback onSend;

  const _MessageInput({required this.controller, required this.isSending, required this.onSend});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      color: MetrixColors.surface,
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              minLines: 1,
              maxLines: 4,
              style: const TextStyle(fontFamily: 'Inter', fontSize: 14),
              decoration: InputDecoration(
                hintText: 'Сообщение...',
                filled: true,
                fillColor: MetrixColors.surfaceMuted,
                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(20),
                  borderSide: BorderSide.none,
                ),
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Material(
            color: MetrixColors.primary,
            shape: const CircleBorder(),
            child: InkWell(
              customBorder: const CircleBorder(),
              onTap: isSending ? null : onSend,
              child: Padding(
                padding: const EdgeInsets.all(10),
                child: isSending
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.send_rounded, color: Colors.white, size: 18),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _HistoryRow extends StatelessWidget {
  final TicketHistoryEntryDto entry;

  const _HistoryRow({required this.entry});

  Color _dotColor(String status) {
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
    final statusLabel = TicketStatus.fromValue(entry.status).label;
    final color = _dotColor(entry.status);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 10,
          height: 10,
          margin: const EdgeInsets.only(top: 4),
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(statusLabel, style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13.5, color: color)),
              if (entry.comment != null && entry.comment!.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(entry.comment!, style: const TextStyle(fontSize: 12.5, color: MetrixColors.textMuted)),
              ],
              const SizedBox(height: 2),
              Text(
                '${entry.user ?? 'Система'} · ${entry.createdAt}',
                style: const TextStyle(fontSize: 11, color: MetrixColors.textMuted),
              ),
            ],
          ),
        ),
      ],
    );
  }
}