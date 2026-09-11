class RoundRoutePoint {
  final int order;
  final String pointUuid;
  final String pointName;
  final String location;
  final bool isVisited;
  final int? visitId;

  const RoundRoutePoint({
    required this.order,
    required this.pointUuid,
    required this.pointName,
    required this.location,
    required this.isVisited,
    this.visitId,
  });

  factory RoundRoutePoint.fromJson(Map<String, dynamic> json) {
    return RoundRoutePoint(
      order: json['order'] as int,
      pointUuid: json['point_uuid'] as String,
      pointName: json['point_name'] as String,
      location: json['location'] as String? ?? '',
      isVisited: json['is_visited'] as bool? ?? false,
      visitId: json['visit_id'] as int?,
    );
  }
}

class RoundDetail {
  final int id;
  final String routeName;
  final String status;
  final DateTime plannedStart;
  final DateTime plannedEnd;
  final bool isOverdue;
  final List<RoundRoutePoint> points;
  final int completed;
  final int total;

  const RoundDetail({
    required this.id,
    required this.routeName,
    required this.status,
    required this.plannedStart,
    required this.plannedEnd,
    required this.isOverdue,
    required this.points,
    required this.completed,
    required this.total,
  });

  factory RoundDetail.fromJson(Map<String, dynamic> json) {
    final pointsJson = json['points'] as List<dynamic>? ?? const [];
    return RoundDetail(
      id: json['id'] as int,
      routeName: json['route_name'] as String,
      status: json['status'] as String,
      plannedStart: DateTime.parse(json['planned_start'] as String),
      plannedEnd: DateTime.parse(json['planned_end'] as String),
      isOverdue: json['is_overdue'] as bool? ?? false,
      points: pointsJson.map((e) => RoundRoutePoint.fromJson(e as Map<String, dynamic>)).toList(),
      completed: json['completed'] as int? ?? 0,
      total: json['total'] as int? ?? 0,
    );
  }
}
