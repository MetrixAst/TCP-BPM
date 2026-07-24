import 'dart:convert';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';

import '../network/api_result.dart';
import 'app_database.dart';
import 'outbox_repository.dart';
import '../../features/attendance/data/attendance_repository.dart';
import '../../features/tickets/data/ticket_detail_repository.dart';
import '../../features/tasks/data/tasks_repository.dart';

class SyncWorker {
  final OutboxRepository outboxRepo;
  final AttendanceRepository attendanceRepo;
  final TicketDetailRepository ticketRepo;
  final TasksRepository tasksRepo;

  bool _isSyncing = false;

  SyncWorker({
    required this.outboxRepo,
    required this.attendanceRepo,
    required this.ticketRepo,
    required this.tasksRepo,
  });

  /// Подписывается на изменения сети и запускает синхронизацию при подключении.
  void startListening() {
    Connectivity().onConnectivityChanged.listen((results) {
      final hasConnection = results.any((r) => r != ConnectivityResult.none);
      if (hasConnection) {
        syncNow();
      }
    });
  }

  Future<void> syncNow() async {
    if (_isSyncing) return;
    _isSyncing = true;

    try {
      final pending = await outboxRepo.getPending();
      for (final item in pending) {
        await _processItem(item);
      }
    } finally {
      _isSyncing = false;
    }
  }

  Future<void> _processItem(OutboxItem item) async {
    await outboxRepo.markSyncing(item.id);

    final payload = jsonDecode(item.payloadJson) as Map<String, dynamic>;
    final type = OutboxOperationType.values.firstWhere(
      (t) => t.name == item.operationType,
    );

    try {
      switch (type) {
        case OutboxOperationType.checkin:
          await _syncCheckin(item, payload);
        case OutboxOperationType.ticketMessage:
          await _syncTicketMessage(item, payload);
        case OutboxOperationType.taskTransition:
          await _syncTaskTransition(item, payload);
      }
      await outboxRepo.remove(item.id);
    } catch (e) {
      await outboxRepo.incrementAttempts(item.id, item.attempts);
      await outboxRepo.markFailed(item.id, e.toString());
    }
  }

  Future<void> _syncCheckin(OutboxItem item, Map<String, dynamic> payload) async {
    if (item.filePath == null || !File(item.filePath!).existsSync()) {
      // фото потеряно — не можем повторить, убираем из очереди
      await outboxRepo.remove(item.id);
      return;
    }

    final result = await attendanceRepo.checkin(
      eventType: payload['event_type'] as String,
      photo: File(item.filePath!),
      latitude: (payload['latitude'] as num?)?.toDouble(),
      longitude: (payload['longitude'] as num?)?.toDouble(),
      idempotencyKey: item.idempotencyKey,
    );

    if (result case Failure(:final message)) {
      throw Exception(message);
    }
  }

  Future<void> _syncTicketMessage(OutboxItem item, Map<String, dynamic> payload) async {
    final result = await ticketRepo.sendMessage(
      payload['ticket_id'] as int,
      payload['text'] as String,
      idempotencyKey: item.idempotencyKey,
    );

    if (result case Failure(:final message)) {
      throw Exception(message);
    }
  }

  Future<void> _syncTaskTransition(OutboxItem item, Map<String, dynamic> payload) async {
    final result = await tasksRepo.transition(
      payload['task_id'] as int,
      payload['action'] as String,
      idempotencyKey: item.idempotencyKey,
    );

    if (result case Failure(:final message)) {
      throw Exception(message);
    }
  }
}