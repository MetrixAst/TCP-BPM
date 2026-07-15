class TicketDto {
  final int id;
  final String number;
  final String title;
  final String category;
  final String priority;
  final String status;
  final String room;
  final String createdAt;
  final String? photo;

  const TicketDto({
    required this.id,
    required this.number,
    required this.title,
    required this.category,
    required this.priority,
    required this.status,
    required this.room,
    required this.createdAt,
    this.photo,
  });

  factory TicketDto.fromJson(Map<String, dynamic> json) {
    return TicketDto(
      id: json['id'] as int,
      number: json['number'] as String,
      title: json['title'] as String,
      category: json['category'] as String,
      priority: json['priority'] as String,
      status: json['status'] as String,
      room: json['room'] as String? ?? '',
      createdAt: json['created_at'] as String,
      photo: json['photo'] as String?,
    );
  }
}