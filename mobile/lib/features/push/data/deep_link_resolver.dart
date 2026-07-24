/// Преобразует target_type/target_id из push-уведомления в маршрут go_router.
String? resolveDeepLink({required String? targetType, required String? targetId}) {
  if (targetType == null || targetId == null) return null;

  switch (targetType) {
    case 'task':
      return '/tasks/$targetId';
    case 'ticket':
      return '/tickets/$targetId';
    // 'documents', 'purchases', 'budget', 'requistion' — пока нет
    // соответствующих мобильных экранов, deep-link на них не ведёт.
    default:
      return null;
  }
}