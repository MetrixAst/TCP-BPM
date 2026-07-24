class NotificationDto {
  final int id;
  final String title;
  final String text;
  final String createdDate;
  final String? targetType;
  final int? targetId;
  final String? url;
  final bool isRead;

  const NotificationDto({
    required this.id,
    required this.title,
    required this.text,
    required this.createdDate,
    this.targetType,
    this.targetId,
    this.url,
    required this.isRead,
  });

  factory NotificationDto.fromJson(Map<String, dynamic> json) {
    return NotificationDto(
      id: json['id'] as int,
      title: json['title'] as String,
      text: json['text'] as String,
      createdDate: json['created_date'] as String,
      targetType: json['target_type'] as String?,
      targetId: json['target_id'] as int?,
      url: json['url'] as String?,
      isRead: json['is_read'] as bool,
    );
  }
}