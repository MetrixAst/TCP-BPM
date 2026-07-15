enum TaskStatus {
  created('created', 'Создана'),
  accepted('accepted', 'Принята'),
  rejected('rejected', 'Отклонена'),
  revision('revision', 'На доработке'),
  completed('completed', 'Завершена');

  final String value;
  final String label;
  const TaskStatus(this.value, this.label);

  static TaskStatus fromValue(String value) {
    return TaskStatus.values.firstWhere(
      (s) => s.value == value,
      orElse: () => TaskStatus.created,
    );
  }
}

enum TaskPriority {
  low('low', 'Низкий'),
  medium('medium', 'Средний'),
  high('high', 'Высокий'),
  critical('critical', 'Критический');

  final String value;
  final String label;
  const TaskPriority(this.value, this.label);
}