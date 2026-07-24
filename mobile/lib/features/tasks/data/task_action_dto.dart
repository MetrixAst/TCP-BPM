class TaskActionDto {
  final String title;
  final String color;
  final String action;
  final String? next;

  const TaskActionDto({
    required this.title,
    required this.color,
    required this.action,
    this.next,
  });

  factory TaskActionDto.fromJson(Map<String, dynamic> json) {
    return TaskActionDto(
      title: json['title'] as String,
      color: json['color'] as String,
      action: json['action'] as String,
      next: json['next'] as String?,
    );
  }
}