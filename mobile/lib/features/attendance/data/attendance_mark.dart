class AttendanceMark {
  final String type;
  final String time;

  const AttendanceMark({required this.type, required this.time});

  factory AttendanceMark.fromJson(Map<String, dynamic> json) {
    return AttendanceMark(
      type: json['type'] as String,
      time: json['time'] as String,
    );
  }
}