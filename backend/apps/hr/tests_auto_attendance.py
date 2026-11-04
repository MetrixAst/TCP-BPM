from datetime import date, datetime, time

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from account.models import Department, Employee, UserAccount
from hr.auto_attendance import run_auto_attendance
from hr.enums import CheckInEnum, DayTypeEnum, LeaveStatusEnum
from hr.models import (
    AttendanceRecord, Company, EmployeeWorkSchedule, LeaveRequest, LeaveType, WorkCalendar,
)

MONDAY = date(2026, 11, 2)
SATURDAY = date(2026, 11, 7)


def at(day, hh, mm=0):
    return timezone.make_aware(datetime.combine(day, time(hh, mm)), timezone.get_current_timezone())


class AutoAttendanceTaskTest(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='AA Co', bin_number='111222333444')
        self.dept = Department.objects.create(name='AA Dept', company=self.company)
        user = UserAccount.objects.create_user(username='aa_emp', password='pass', role='staff')
        self.employee = Employee.objects.create(user=user, department=self.dept, status='active')
        self.schedule = EmployeeWorkSchedule.objects.create(
            employee=self.employee, work_start=time(9, 0), work_end=time(18, 0),
            auto_attendance=True,
        )

    def events(self):
        return dict(
            AttendanceRecord.objects.filter(employee=self.employee)
            .values_list('event_type', 'timestamp')
        )

    def test_nothing_before_work_start(self):
        self.assertEqual(run_auto_attendance(at(MONDAY, 8, 55)), 0)
        self.assertEqual(self.events(), {})

    def test_day_start_at_schedule_time(self):
        self.assertEqual(run_auto_attendance(at(MONDAY, 9, 3)), 1)
        events = self.events()
        self.assertEqual(events, {CheckInEnum.DAY_START: at(MONDAY, 9)})
        record = AttendanceRecord.objects.get()
        self.assertEqual(record.source, AttendanceRecord.SOURCE_AUTO)
        self.assertFalse(record.is_manual)

    def test_full_day_and_idempotent(self):
        run_auto_attendance(at(MONDAY, 9, 1))
        run_auto_attendance(at(MONDAY, 18, 2))
        self.assertEqual(run_auto_attendance(at(MONDAY, 18, 7)), 0)
        self.assertEqual(self.events(), {
            CheckInEnum.DAY_START: at(MONDAY, 9),
            CheckInEnum.DAY_END: at(MONDAY, 18),
        })

    def test_catches_up_whole_day_after_downtime(self):
        self.assertEqual(run_auto_attendance(at(MONDAY, 19)), 2)

    @override_settings(ATTENDANCE_DISABLED_TYPES=[])
    def test_lunch_marks_when_schedule_has_lunch(self):
        self.schedule.lunch_start = time(13, 0)
        self.schedule.lunch_end = time(14, 0)
        self.schedule.save()
        run_auto_attendance(at(MONDAY, 13, 30))
        self.assertEqual(set(self.events()), {CheckInEnum.DAY_START, CheckInEnum.LUNCH_START})

    def test_keeps_own_check_in(self):
        AttendanceRecord.objects.create(
            employee=self.employee, event_type=CheckInEnum.DAY_START,
            timestamp=at(MONDAY, 8, 40), source=AttendanceRecord.SOURCE_QR,
        )
        self.assertEqual(run_auto_attendance(at(MONDAY, 9, 5)), 0)
        self.assertEqual(self.events()[CheckInEnum.DAY_START], at(MONDAY, 8, 40))

    def test_disabled_flag(self):
        self.schedule.auto_attendance = False
        self.schedule.save()
        self.assertEqual(run_auto_attendance(at(MONDAY, 19)), 0)

    def test_skips_weekend(self):
        self.assertEqual(run_auto_attendance(at(SATURDAY, 19)), 0)

    def test_skips_holiday_in_calendar(self):
        WorkCalendar.objects.create(company=None, date=MONDAY, day_type=DayTypeEnum.HOLIDAY)
        self.assertEqual(run_auto_attendance(at(MONDAY, 19)), 0)

    def test_skips_vacation_status_and_dismissed(self):
        for status in ('vacation', 'sick_leave', 'dismissed'):
            self.employee.status = status
            self.employee.save()
            self.assertEqual(run_auto_attendance(at(MONDAY, 19)), 0, status)

    def test_skips_approved_leave(self):
        leave_type = LeaveType.objects.create(name='Ежегодный')
        LeaveRequest.objects.create(
            employee=self.employee, leave_type=leave_type,
            start_date=MONDAY, end_date=MONDAY, status=LeaveStatusEnum.APPROVED,
        )
        self.assertEqual(run_auto_attendance(at(MONDAY, 19)), 0)

    def test_inactive_user_skipped(self):
        self.employee.user.is_active = False
        self.employee.user.save()
        self.assertEqual(run_auto_attendance(at(MONDAY, 19)), 0)


class AutoAttendanceSettingsTest(TestCase):

    def setUp(self):
        company = Company.objects.create(name='AA2 Co', bin_number='555666777888')
        dept = Department.objects.create(name='AA2 Dept', company=company)
        self.admin = UserAccount.objects.create_user(username='aa_admin', password='pass', role='administrator')
        self.hr = UserAccount.objects.create_user(username='aa_hr', password='pass', role='hr')
        u1 = UserAccount.objects.create_user(username='aa_e1', password='pass', role='staff')
        u2 = UserAccount.objects.create_user(username='aa_e2', password='pass', role='staff')
        self.e1 = Employee.objects.create(user=u1, department=dept, status='active')
        self.e2 = Employee.objects.create(user=u2, department=dept, status='active')
        EmployeeWorkSchedule.objects.create(employee=self.e2, auto_attendance=True)

    def test_hr_has_no_access(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(reverse('hr:auto_attendance')).status_code, 403)

    def test_admin_bulk_toggle(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('hr:auto_attendance'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'aa_e1')

        self.client.post(reverse('hr:auto_attendance'), {'employees': [self.e1.pk]})

        self.assertTrue(EmployeeWorkSchedule.objects.get(employee=self.e1).auto_attendance)
        self.assertFalse(EmployeeWorkSchedule.objects.get(employee=self.e2).auto_attendance)

    def test_hr_schedule_save_keeps_auto_flag(self):
        self.client.force_login(self.hr)
        self.client.post(reverse('hr:employee_schedule', args=[self.e2.pk]), {
            'work_start': '08:00', 'work_end': '17:00', 'grace_minutes': 0, 'workdays': ['0', '1'],
        })
        schedule = EmployeeWorkSchedule.objects.get(employee=self.e2)
        self.assertEqual(schedule.work_start, time(8, 0))
        self.assertTrue(schedule.auto_attendance)

    def test_admin_schedule_form_toggles_auto(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('hr:employee_schedule', args=[self.e1.pk]), {
            'work_start': '09:00', 'work_end': '18:00', 'grace_minutes': 0,
            'workdays': ['0', '1', '2', '3', '4'], 'auto_attendance': 'on',
        })
        self.assertTrue(EmployeeWorkSchedule.objects.get(employee=self.e1).auto_attendance)
