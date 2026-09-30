import 'checkin_event_type.dart';

class AttendanceTodayStatus {
  final CheckinEventType type;
  final String? time;
  final String? photoUrl;
  final String? locationAddress;

  const AttendanceTodayStatus({
    required this.type,
    this.time,
    this.photoUrl,
    this.locationAddress,
  });

  bool get isCompleted => time != null;

  /// Сервер отдаёт ISO-строку в UTC (`2026-09-30T03:47:00+00:00`), а в
  /// интерфейсе нужно местное время отметки в виде `08:47`.
  String? get timeLabel {
    final raw = time;
    if (raw == null) return null;

    final parsed = DateTime.tryParse(raw);
    if (parsed == null) return raw;

    final local = parsed.toLocal();
    final hh = local.hour.toString().padLeft(2, '0');
    final mm = local.minute.toString().padLeft(2, '0');
    return '$hh:$mm';
  }
}

List<AttendanceTodayStatus> buildTodayStatus(List<dynamic> marksJson) {
  final marksByType = <String, Map<String, dynamic>>{};
  for (final m in marksJson) {
    final map = m as Map<String, dynamic>;
    marksByType[map['type'] as String] = map;
  }

  return CheckinEventType.values.map((type) {
    final mark = marksByType[type.value];
    return AttendanceTodayStatus(
      type: type,
      time: mark?['time'] as String?,
      photoUrl: mark?['photo'] as String?,
      locationAddress: mark?['location_address'] as String?,
    );
  }).toList();
}