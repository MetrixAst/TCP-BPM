import 'package:flutter_test/flutter_test.dart';
import 'package:metrix_app/features/tasks/data/task_dto.dart';

TaskDto taskWithDeadline(String? deadline) {
  return TaskDto.fromJson({
    'id': 1,
    'title': 'Проверить показания счётчиков',
    'text': '',
    'status': 'accepted',
    'status_display': 'Принята',
    'status_color': 'info',
    'priority': 'medium',
    'priority_display': 'Средний',
    'deadline': deadline,
    'date': '2026-09-30',
    'author': {'id': 2, 'username': 'admin', 'name': 'Администратор'},
  });
}

void main() {
  test('срок из API показывается в привычном порядке', () {
    expect(taskWithDeadline('2026-10-06').deadlineLabel, '06.10.2026');
  });

  test('день и месяц дополняются нулём', () {
    expect(taskWithDeadline('2026-01-02').deadlineLabel, '02.01.2026');
  });

  test('без срока подписи нет', () {
    expect(taskWithDeadline(null).deadlineLabel, isNull);
  });

  test('неразобранное значение отдаётся как есть', () {
    expect(taskWithDeadline('когда-нибудь').deadlineLabel, 'когда-нибудь');
  });
}
