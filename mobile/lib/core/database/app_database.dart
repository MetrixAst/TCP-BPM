import 'dart:io';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

part 'app_database.g.dart';

enum OutboxOperationType { checkin, ticketMessage, taskTransition }

enum OutboxStatus { pending, syncing, failed }

/// Очередь мутаций, ожидающих отправки на сервер.
class OutboxItems extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get idempotencyKey => text().unique()();
  TextColumn get operationType => text()(); // OutboxOperationType.name
  TextColumn get payloadJson => text()(); // сериализованные данные для запроса
  TextColumn get filePath => text().nullable()(); // путь к фото, если есть
  TextColumn get status => text().withDefault(const Constant('pending'))();
  IntColumn get attempts => integer().withDefault(const Constant(0))();
  TextColumn get lastError => text().nullable()();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
}

/// Read-кэш списка заявок для офлайн-просмотра.
class CachedTickets extends Table {
  IntColumn get id => integer()();
  TextColumn get dataJson => text()();
  DateTimeColumn get cachedAt => dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {id};
}

/// Read-кэш списка задач для офлайн-просмотра.
class CachedTasks extends Table {
  IntColumn get id => integer()();
  TextColumn get dataJson => text()();
  DateTimeColumn get cachedAt => dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {id};
}

@DriftDatabase(tables: [OutboxItems, CachedTickets, CachedTasks])
class AppDatabase extends _$AppDatabase {
  AppDatabase() : super(_openConnection());

  static AppDatabase? _instance;
  static AppDatabase get instance => _instance ??= AppDatabase();

  @override
  int get schemaVersion => 1;
}

LazyDatabase _openConnection() {
  return LazyDatabase(() async {
    final dbFolder = await getApplicationDocumentsDirectory();
    final file = File(p.join(dbFolder.path, 'metrix_offline.sqlite'));
    return NativeDatabase.createInBackground(file);
  });
}