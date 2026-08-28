enum CheckinEventType {
  dayStart('day_start', 'Приход'),
  dayEnd('day_end', 'Уход');

  final String value;
  final String label;

  const CheckinEventType(this.value, this.label);
}