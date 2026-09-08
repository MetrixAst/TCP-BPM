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

class RoundPointDetail {
  final String pointUuid;
  final String pointName;
  final String location;
  final List<RoundChecklistItem> items;
  final bool alreadyVisited;

  const RoundPointDetail({
    required this.pointUuid,
    required this.pointName,
    required this.location,
    required this.items,
    required this.alreadyVisited,
  });

  factory RoundPointDetail.fromJson(Map<String, dynamic> json) {
    final itemsJson = json['items'] as List<dynamic>? ?? const [];
    return RoundPointDetail(
      pointUuid: json['point_uuid'] as String,
      pointName: json['point_name'] as String,
      location: json['location'] as String? ?? '',
      items: itemsJson
          .map((e) => RoundChecklistItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      alreadyVisited: json['already_visited'] as bool? ?? false,
    );
  }
}
