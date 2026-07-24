class TaskHistoryEntryDto {
  final int id;
  final String status;
  final String statusDisplay;
  final String date;
  final String? user;

  const TaskHistoryEntryDto({
    required this.id,
    required this.status,
    required this.statusDisplay,
    required this.date,
    this.user,
  });

  factory TaskHistoryEntryDto.fromJson(Map<String, dynamic> json) {
    return TaskHistoryEntryDto(
      id: json['id'] as int,
      status: json['status'] as String,
      statusDisplay: json['status_display'] as String,
      date: json['date'] as String,
      user: json['user'] as String?,
    );
  }
}