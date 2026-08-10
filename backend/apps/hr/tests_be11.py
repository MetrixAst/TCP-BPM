from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from account.models import UserAccount, Employee, Department
from hr.models import AttendanceRecord, Company
from hr.enums import CheckInEnum


def make_setup():
    company = Company.objects.create(name='Test Co', bin_number='123456789012')
    dept = Department.objects.create(name='Test Dept', company=company)
    user = UserAccount.objects.create_user(username='test_att', password='pass', role='staff')
    employee = Employee.objects.create(user=user, department=dept)
    return employee


class AttendanceDisabledTypesTest(TestCase):

    def setUp(self):
        self.employee = make_setup()

    @override_settings(ATTENDANCE_DISABLED_TYPES=['lunch_start', 'lunch_end'])
    def test_lunch_start_blocked(self):
        record = AttendanceRecord(
            employee=self.employee,
            event_type=CheckInEnum.LUNCH_START,
            timestamp=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            record.clean()

    @override_settings(ATTENDANCE_DISABLED_TYPES=['lunch_start', 'lunch_end'])
    def test_lunch_end_blocked(self):
        record = AttendanceRecord(
            employee=self.employee,
            event_type=CheckInEnum.LUNCH_END,
            timestamp=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            record.clean()

    @override_settings(ATTENDANCE_DISABLED_TYPES=['lunch_start', 'lunch_end'])
    def test_day_start_allowed(self):
        record = AttendanceRecord(
            employee=self.employee,
            event_type=CheckInEnum.DAY_START,
            timestamp=timezone.now(),
        )
        try:
            record.clean()
        except ValidationError as e:
            if 'отключён' in str(e):
                self.fail('DAY_START не должен быть заблокирован')

    @override_settings(ATTENDANCE_DISABLED_TYPES=[])
    def test_lunch_allowed_when_enabled(self):
        record = AttendanceRecord(
            employee=self.employee,
            event_type=CheckInEnum.LUNCH_START,
            timestamp=timezone.now(),
        )
        try:
            record.clean()
        except ValidationError as e:
            if 'отключён' in str(e):
                self.fail('LUNCH_START должен быть разрешён когда список пуст')

    def test_old_lunch_records_preserved(self):
        AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=self.employee,
                event_type=CheckInEnum.LUNCH_START,
                timestamp=timezone.now() - timezone.timedelta(days=10),
            )
        ])
        self.assertEqual(
            AttendanceRecord.objects.filter(
                employee=self.employee,
                event_type=CheckInEnum.LUNCH_START,
            ).count(),
            1,
        )