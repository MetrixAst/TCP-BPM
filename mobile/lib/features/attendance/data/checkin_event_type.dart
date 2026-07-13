enum CheckinEventType {
  dayStart('day_start', 'Приход'),
  lunchStart('lunch_start', 'Начало обеда'),
  lunchEnd('lunch_end', 'Конец обеда'),
  dayEnd('day_end', 'Уход');

  final String value;
  final String label;

  const CheckinEventType(this.value, this.label);
}