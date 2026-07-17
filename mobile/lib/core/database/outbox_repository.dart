import 'dart:convert';

import 'package:uuid/uuid.dart';

import 'app_database.dart';

import 'package:drift/drift.dart';

class OutboxRepository {
  final AppDatabase db;
  final _uuid = const Uuid();

  OutboxRepository({required this.db});

  /// Добавляет мутацию в очередь. Возвращает сгенерированный idempotency-key.
  Future<String> enqueue({
    required OutboxOperationType type,
    required Map<String, dynamic> payload,
    String? filePath,
  }) async {
    final key = _uuid.v4();
    await db.into(db.outboxItems).insert(
      OutboxItemsCompanion.insert(
        idempotencyKey: key,
        operationType: type.name,
        payloadJson: jsonEncode(payload),
        filePath: Value(filePath),
      ),
    );
    return key;
  }

  Future<List<OutboxItem>> getPending() {
    return (db.select(db.outboxItems)
      ..where((t) => t.status.equals(OutboxStatus.pending.name))
      ..orderBy([(t) => OrderingTerm.asc(t.createdAt)]))
        .get();
  }

  Future<void> markSyncing(int id) {
    return (db.update(db.outboxItems)..where((t) => t.id.equals(id))).write(
      const OutboxItemsCompanion(status: Value('syncing')),
    );
  }

  Future<void> markFailed(int id, String error) {
    return (db.update(db.outboxItems)..where((t) => t.id.equals(id))).write(
      OutboxItemsCompanion(
        status: const Value('pending'), // возвращаем в очередь для повтора
        lastError: Value(error),
        attempts: Value.absent(),
      ),
    );
  }

  Future<void> incrementAttempts(int id, int currentAttempts) {
    return (db.update(db.outboxItems)..where((t) => t.id.equals(id))).write(
      OutboxItemsCompanion(attempts: Value(currentAttempts + 1)),
    );
  }

  Future<void> remove(int id) {
    return (db.delete(db.outboxItems)..where((t) => t.id.equals(id))).go();
  }

  Future<int> countPending() async {
    final items = await getPending();
    return items.length;
  }

  Stream<int> watchPendingCount() {
    final query = db.select(db.outboxItems)
      ..where((t) => t.status.equals(OutboxStatus.pending.name));
    return query.watch().map((rows) => rows.length);
  }
}