// Отчёт по помещению для руководителя или админа, отсканировавшего QR.

class RoundReportChecklist {
  final String? checklistName;
  final String assignee;
  final int intervalHours;
  final bool isOverdue;
  final DateTime? lastVisitAt;
  final String? lastVisitBy;

  const RoundReportChecklist({
    required this.checklistName,
    required this.assignee,
    required this.intervalHours,
    required this.isOverdue,
    this.lastVisitAt,
    this.lastVisitBy,
  });

  factory RoundReportChecklist.fromJson(Map<String, dynamic> json) {
    return RoundReportChecklist(
      checklistName: json['checklist_name'] as String?,
      assignee: json['assignee'] as String? ?? '',
      intervalHours: json['interval_hours'] as int? ?? 0,
      isOverdue: json['is_overdue'] as bool? ?? false,
      lastVisitAt: _date(json['last_visit_at']),
      lastVisitBy: json['last_visit_by'] as String?,
    );
  }
}

class RoundReportDefect {
  final String description;
  // По какому чек-листу записана неисправность: электрика, сантехника, клининг…
  final String? checklistName;
  final DateTime? createdAt;
  final String? reportedBy;

  const RoundReportDefect({required this.description, this.checklistName, this.createdAt, this.reportedBy});

  factory RoundReportDefect.fromJson(Map<String, dynamic> json) {
    return RoundReportDefect(
      description: json['description'] as String? ?? '',
      checklistName: json['checklist_name'] as String?,
      createdAt: _date(json['created_at']),
      reportedBy: json['reported_by'] as String?,
    );
  }
}

class RoundReportVisit {
  final DateTime? createdAt;
  final String employeeName;
  final String? checklistName;
  final int failedCount;
  final String comment;

  const RoundReportVisit({
    this.createdAt,
    required this.employeeName,
    this.checklistName,
    required this.failedCount,
    this.comment = '',
  });

  factory RoundReportVisit.fromJson(Map<String, dynamic> json) {
    return RoundReportVisit(
      createdAt: _date(json['created_at']),
      employeeName: json['employee_name'] as String? ?? '',
      checklistName: json['checklist_name'] as String?,
      failedCount: json['failed_count'] as int? ?? 0,
      comment: json['comment'] as String? ?? '',
    );
  }
}

class RoundPointReport {
  final String pointName;
  final String location;
  final bool isOverdue;
  final List<RoundReportChecklist> checklists;
  final List<RoundReportDefect> openDefects;
  final List<RoundReportVisit> recentVisits;

  const RoundPointReport({
    required this.pointName,
    required this.location,
    required this.isOverdue,
    required this.checklists,
    required this.openDefects,
    required this.recentVisits,
  });

  factory RoundPointReport.fromJson(Map<String, dynamic> json) {
    List<T> list<T>(String key, T Function(Map<String, dynamic>) parse) =>
        (json[key] as List<dynamic>? ?? const []).map((e) => parse(e as Map<String, dynamic>)).toList();
    return RoundPointReport(
      pointName: json['point_name'] as String? ?? '',
      location: json['location'] as String? ?? '',
      isOverdue: json['is_overdue'] as bool? ?? false,
      checklists: list('checklists', RoundReportChecklist.fromJson),
      openDefects: list('open_defects', RoundReportDefect.fromJson),
      recentVisits: list('recent_visits', RoundReportVisit.fromJson),
    );
  }
}

DateTime? _date(Object? value) => value is String ? DateTime.tryParse(value)?.toLocal() : null;
