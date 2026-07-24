class TicketMessageAuthorDto {
  final int id;
  final String fullName;

  const TicketMessageAuthorDto({required this.id, required this.fullName});

  factory TicketMessageAuthorDto.fromJson(Map<String, dynamic> json) {
    return TicketMessageAuthorDto(
      id: json['id'] as int,
      fullName: json['full_name'] as String,
    );
  }
}

class TicketMessageDto {
  final int id;
  final TicketMessageAuthorDto? author;
  final String text;
  final String createdAt;

  const TicketMessageDto({
    required this.id,
    this.author,
    required this.text,
    required this.createdAt,
  });

  factory TicketMessageDto.fromJson(Map<String, dynamic> json) {
    return TicketMessageDto(
      id: json['id'] as int,
      author: json['author'] != null
          ? TicketMessageAuthorDto.fromJson(json['author'] as Map<String, dynamic>)
          : null,
      text: json['text'] as String,
      createdAt: json['created_at'] as String,
    );
  }
}