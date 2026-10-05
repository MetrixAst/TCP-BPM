/// Web: офлайн-очередь на Drift/sqlite недоступна — очистка no-op.
class LocalDataCleaner {
  LocalDataCleaner({Object? db});

  Future<void> clear() async {}
}
