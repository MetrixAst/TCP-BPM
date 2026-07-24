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