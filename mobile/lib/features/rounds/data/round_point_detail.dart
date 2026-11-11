class RoundChecklistItem {
  final int id;
  final String text;
  final bool requiresPhotoOnFail;

  const RoundChecklistItem({
    required this.id,
    required this.text,
    required this.requiresPhotoOnFail,
  });

  factory RoundChecklistItem.fromJson(Map<String, dynamic> json) {
    return RoundChecklistItem(
      id: json['id'] as int,
      text: json['text'] as String,
      requiresPhotoOnFail: json['requires_photo_on_fail'] as bool? ?? false,
    );
  }
}

/// Чек-лист, который сотрудник может пройти на точке. На одном помещении
/// у сантехника, электрика и клининга — свои чек-листы.
class RoundChecklistOption {
  final int id;
  final String name;

  const RoundChecklistOption({required this.id, required this.name});

  factory RoundChecklistOption.fromJson(Map<String, dynamic> json) {
    return RoundChecklistOption(id: json['id'] as int, name: json['name'] as String? ?? '');
  }
}

class RoundPointDetail {
  final String pointUuid;
  final String pointName;
  final String location;
  final int? checklistId;
  final String? checklistName;
  final List<RoundChecklistOption> checklists;
  final List<RoundChecklistItem> items;
  final bool alreadyVisited;

  const RoundPointDetail({
    required this.pointUuid,
    required this.pointName,
    required this.location,
    this.checklistId,
    this.checklistName,
    this.checklists = const [],
    required this.items,
    required this.alreadyVisited,
  });

  factory RoundPointDetail.fromJson(Map<String, dynamic> json) {
    final itemsJson = json['items'] as List<dynamic>? ?? const [];
    final checklistsJson = json['checklists'] as List<dynamic>? ?? const [];
    return RoundPointDetail(
      pointUuid: json['point_uuid'] as String,
      pointName: json['point_name'] as String,
      location: json['location'] as String? ?? '',
      checklistId: json['checklist_id'] as int?,
      checklistName: json['checklist_name'] as String?,
      checklists: checklistsJson
          .map((e) => RoundChecklistOption.fromJson(e as Map<String, dynamic>))
          .toList(),
      items: itemsJson
          .map((e) => RoundChecklistItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      alreadyVisited: json['already_visited'] as bool? ?? false,
    );
  }
}
