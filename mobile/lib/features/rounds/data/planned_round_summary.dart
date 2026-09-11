class PlannedRoundSummary {
  final int id;
  final String routeName;
  final String status;
  final DateTime plannedStart;
  final DateTime plannedEnd;
  final DateTime? completedAt;
  final bool isOverdue;
  final int totalPoints;
  final int completedPoints;

  const PlannedRoundSummary({
    required this.id,
    required this.routeName,
    required this.status,
    required this.plannedStart,
    required this.plannedEnd,
    this.completedAt,
    required this.isOverdue,
    required this.totalPoints,
    required this.completedPoints,
  });

  factory PlannedRoundSummary.fromJson(Map<String, dynamic> json) {
    return PlannedRoundSummary(
      id: json['id'] as int,
      routeName: json['route_name'] as String,
      status: json['status'] as String,
      plannedStart: DateTime.parse(json['planned_start'] as String),
      plannedEnd: DateTime.parse(json['planned_end'] as String),
      completedAt: json['completed_at'] != null ? DateTime.parse(json['completed_at'] as String) : null,
      isOverdue: json['is_overdue'] as bool? ?? false,
      totalPoints: json['total_points'] as int? ?? 0,
      completedPoints: json['completed_points'] as int? ?? 0,
    );
  }

  int get progressPercent => totalPoints == 0 ? 0 : (completedPoints * 100 / totalPoints).round();
}
