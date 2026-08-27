import 'task_action_dto.dart';
import 'task_history_dto.dart';

class TaskUserDto {
  final int id;
  final String username;
  final String name;

  const TaskUserDto({required this.id, required this.username, required this.name});

  factory TaskUserDto.fromJson(Map<String, dynamic> json) {
    return TaskUserDto(
      id: json['id'] as int,
      username: json['username'] as String,
      name: json['name'] as String,
    );
  }
}

class TaskDto {
  final int id;
  final String title;
  final String text;
  final String status;
  final String statusDisplay;
  final String statusColor;
  final String priority;
  final String priorityDisplay;
  final String? deadline;
  final String date;
  final int views;
  final TaskUserDto author;
  final TaskUserDto? executor;
  final List<TaskActionDto> availableActions;
  final bool canDelete;
  final List<TaskHistoryEntryDto> history;

  const TaskDto({
    required this.id,
    required this.title,
    required this.text,
    required this.status,
    required this.statusDisplay,
    required this.statusColor,
    required this.priority,
    required this.priorityDisplay,
    this.deadline,
    required this.date,
    required this.views,
    required this.author,
    this.executor,
    required this.availableActions,
    required this.canDelete,
    required this.history,
  });

  factory TaskDto.fromJson(Map<String, dynamic> json) {
    return TaskDto(
      id: json['id'] as int,
      title: json['title'] as String,
      text: json['text'] as String? ?? '',
      status: json['status'] as String,
      statusDisplay: json['status_display'] as String,
      statusColor: json['status_color'] as String,
      priority: json['priority'] as String,
      priorityDisplay: json['priority_display'] as String,
      deadline: json['deadline'] as String?,
      date: json['date'] as String,
      views: json['views'] as int? ?? 0,
      author: TaskUserDto.fromJson(json['author'] as Map<String, dynamic>),
      executor: json['executor'] != null
          ? TaskUserDto.fromJson(json['executor'] as Map<String, dynamic>)
          : null,
      availableActions: (json['available_actions'] as List<dynamic>? ?? [])
          .map((a) => TaskActionDto.fromJson(a as Map<String, dynamic>))
          .toList(),
      canDelete: json['can_delete'] as bool? ?? false,
      history: (json['history'] as List<dynamic>? ?? [])
          .map((h) => TaskHistoryEntryDto.fromJson(h as Map<String, dynamic>))
          .toList(),
    );
  }
}