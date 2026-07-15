enum TicketCategory {
  electrical('electrical', 'Электрика'),
  plumbing('plumbing', 'Сантехника'),
  hvac('hvac', 'Вентиляция и кондиционирование'),
  cleaning('cleaning', 'Клининг'),
  furniture('furniture', 'Мебель и фурнитура'),
  it('it', 'ИТ и связь'),
  security('security', 'Безопасность'),
  other('other', 'Прочее');

  final String value;
  final String label;
  const TicketCategory(this.value, this.label);

  static TicketCategory fromValue(String value) {
    return TicketCategory.values.firstWhere(
          (c) => c.value == value,
      orElse: () => TicketCategory.other,
    );
  }
}

enum TicketPriority {
  low('low', 'Низкий'),
  medium('medium', 'Средний'),
  high('high', 'Высокий'),
  urgent('urgent', 'Срочный');

  final String value;
  final String label;
  const TicketPriority(this.value, this.label);

  static TicketPriority fromValue(String value) {
    return TicketPriority.values.firstWhere(
          (p) => p.value == value,
      orElse: () => TicketPriority.medium,
    );
  }
}

enum TicketStatus {
  newStatus('new', 'Новая'),
  accepted('accepted', 'Принята'),
  inProgress('in_progress', 'В работе'),
  done('done', 'Выполнена'),
  rejected('rejected', 'Отклонена'),
  cancelled('cancelled', 'Отменена');

  final String value;
  final String label;
  const TicketStatus(this.value, this.label);

  static TicketStatus fromValue(String value) {
    return TicketStatus.values.firstWhere(
          (s) => s.value == value,
      orElse: () => TicketStatus.newStatus,
    );
  }
}