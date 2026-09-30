import 'dart:io';

import 'app_database.dart';

/// Удаляет локальные данные аккаунта: офлайн-кэш и неотправленную очередь.
///
/// Без этого следующий пользователь на том же устройстве видит чужие заявки,
/// а отложенные операции уезжают на сервер, к которому они не относятся.
class LocalDataCleaner {
  final AppDatabase Function() _db;

  LocalDataCleaner({AppDatabase? db})
      : _db = (db != null ? (() => db) : (() => AppDatabase.instance));

  Future<void> clear() async {
    final db = _db();
    final queued = await db.select(db.outboxItems).get();

    await db.batch((batch) {
      batch.deleteAll(db.outboxItems);
      batch.deleteAll(db.cachedTickets);
      batch.deleteAll(db.cachedTasks);
    });

    for (final item in queued) {
      final path = item.filePath;
      if (path == null) continue;
      try {
        final file = File(path);
        if (file.existsSync()) await file.delete();
      } catch (_) {
        // Файл мог быть удалён системой — очистку это прерывать не должно.
      }
    }
  }
}
