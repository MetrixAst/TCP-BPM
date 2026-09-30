import 'package:flutter_test/flutter_test.dart';
import 'package:metrix_app/features/attendance/data/attendance_today_status.dart';
import 'package:metrix_app/features/attendance/data/checkin_event_type.dart';

void main() {
  group('buildTodayStatus', () {
    test('возвращает строку на каждый тип отметки', () {
      final statuses = buildTodayStatus([]);

      expect(statuses.length, CheckinEventType.values.length);
      expect(statuses.every((s) => !s.isCompleted), isTrue);
    });

    test('сопоставляет отметку с её типом', () {
      final statuses = buildTodayStatus([
        {'type': 'day_start', 'time': '2026-09-30T03:47:00+00:00', 'photo': null},
      ]);

      final start = statuses.firstWhere((s) => s.type == CheckinEventType.dayStart);
      final end = statuses.firstWhere((s) => s.type == CheckinEventType.dayEnd);

      expect(start.isCompleted, isTrue);
      expect(end.isCompleted, isFalse);
    });
  });

  group('timeLabel', () {
    test('переводит UTC из API в местное время вида ЧЧ:ММ', () {
      const raw = '2026-09-30T03:47:00+00:00';
      const status = AttendanceTodayStatus(
        type: CheckinEventType.dayStart,
        time: raw,
      );

      final local = DateTime.parse(raw).toLocal();
      final expected = '${local.hour.toString().padLeft(2, '0')}:'
          '${local.minute.toString().padLeft(2, '0')}';

      expect(status.timeLabel, expected);
      expect(status.timeLabel, isNot(contains('T')));
    });

    test('без отметки времени нет', () {
      const status = AttendanceTodayStatus(type: CheckinEventType.dayEnd);

      expect(status.timeLabel, isNull);
    });

    test('неразобранное значение отдаётся как есть, а не роняет экран', () {
      const status = AttendanceTodayStatus(
        type: CheckinEventType.dayStart,
        time: 'не время',
      );

      expect(status.timeLabel, 'не время');
    });
  });
}
