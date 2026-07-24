class TicketAttachmentDto {
  final int id;
  final String? file;
  final String originalName;
  final String createdAt;

  const TicketAttachmentDto({
    required this.id,
    this.file,
    required this.originalName,
    required this.createdAt,
  });

  factory TicketAttachmentDto.fromJson(Map<String, dynamic> json) {
    return TicketAttachmentDto(
      id: json['id'] as int,
      file: json['file'] as String?,
      originalName: json['original_name'] as String,
      createdAt: json['created_at'] as String,
    );
  }
}

class TicketDetailDto {
  final int id;
  final String number;
  final String title;
  final String description;
  final String category;
  final String priority;
  final String status;
  final String room;
  final String createdAt;
  final String updatedAt;
  final String? photo;
  final List<TicketAttachmentDto> attachments;
  final List<TicketHistoryEntryDto> history;

  const TicketDetailDto({
    required this.id,
    required this.number,
    required this.title,
    required this.description,
    required this.category,
    required this.priority,
    required this.status,
    required this.room,
    required this.createdAt,
    required this.updatedAt,
    this.photo,
    required this.attachments,
    required this.history,
  });

  factory TicketDetailDto.fromJson(Map<String, dynamic> json) {
    return TicketDetailDto(
      id: json['id'] as int,
      number: json['number'] as String,
      title: json['title'] as String,
      description: json['description'] as String,
      category: json['category'] as String,
      priority: json['priority'] as String,
      status: json['status'] as String,
      room: json['room'] as String? ?? '',
      createdAt: json['created_at'] as String,
      updatedAt: json['updated_at'] as String,
      photo: json['photo'] as String?,
      attachments: (json['attachments'] as List<dynamic>? ?? [])
          .map((a) => TicketAttachmentDto.fromJson(a as Map<String, dynamic>))
          .toList(),
      history: (json['history'] as List<dynamic>? ?? [])
          .map((h) => TicketHistoryEntryDto.fromJson(h as Map<String, dynamic>))
          .toList(),
    );
  }
}

class TicketHistoryEntryDto {
  final int id;
  final String status;
  final String? comment;
  final String createdAt;
  final String? user;

  const TicketHistoryEntryDto({
    required this.id,
    required this.status,
    this.comment,
    required this.createdAt,
    this.user,
  });

  factory TicketHistoryEntryDto.fromJson(Map<String, dynamic> json) {
    return TicketHistoryEntryDto(
      id: json['id'] as int,
      status: json['status'] as String,
      comment: json['comment'] as String?,
      createdAt: json['created_at'] as String,
      user: json['user'] as String?,
    );
  }
}