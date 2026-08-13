from django.test import TestCase
from django.utils import timezone

from account.models import UserAccount, Employee, Department
from hr.models import Company, AttendanceRecord, AttendanceManualReason
from hr.enums import CheckInEnum


def make_setup():
    company = Company.objects.create(name='BE19 Co', bin_number='555444333222')
    dept = Department.objects.create(name='BE19 Dept', company=company)
    user = UserAccount.objects.create_user(username='emp_be19', password='pass', role='staff')
    hr_user = UserAccount.objects.create_user(username='hr_be19', password='pass', role='hr')
    employee = Employee.objects.create(user=user, department=dept)
    return employee, hr_user


class AttendanceManualReasonTest(TestCase):

    def test_create_reason(self):
        reason = AttendanceManualReason.objects.create(
            code='test_reason',
            label='Тестовое основание',
        )
        self.assertTrue(reason.is_active)
        self.assertEqual(str(reason), 'Тестовое основание')

    def test_seed_creates_reasons(self):
        from django.core.management import call_command
        call_command('seed_manual_reasons', verbosity=0)
        self.assertGreater(AttendanceManualReason.objects.count(), 0)
        self.assertTrue(AttendanceManualReason.objects.filter(code='sick_leave').exists())
        self.assertTrue(AttendanceManualReason.objects.filter(code='business_trip').exists())


class ManualAttendanceRecordTest(TestCase):

    def setUp(self):
        self.employee, self.hr_user = make_setup()
        self.reason = AttendanceManualReason.objects.create(
            code='be19_reason',
            label='Тест основание',
        )

    def test_manual_record_has_all_fields(self):
        record = AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=self.employee,
                event_type=CheckInEnum.DAY_START,
                timestamp=timezone.now(),
                is_manual=True,
                manual_author=self.hr_user,
                manual_reason=self.reason,
                manual_comment='Сотрудник опоздал по уважительной причине',
            )
        ])[0]
        record.refresh_from_db()
        self.assertTrue(record.is_manual)
        self.assertEqual(record.manual_author, self.hr_user)
        self.assertEqual(record.manual_reason, self.reason)
        self.assertEqual(record.manual_comment, 'Сотрудник опоздал по уважительной причине')

    def test_automatic_record_compatible(self):
        record = AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=self.employee,
                event_type=CheckInEnum.DAY_END,
                timestamp=timezone.now(),
            )
        ])[0]
        record.refresh_from_db()
        self.assertFalse(record.is_manual)
        self.assertIsNone(record.manual_author)
        self.assertIsNone(record.manual_reason)
        self.assertEqual(record.manual_comment, '')

    def test_multiple_auto_records_no_conflict(self):
        AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=self.employee,
                event_type=CheckInEnum.DAY_START,
                timestamp=timezone.now(),
            ),
        ])
        self.assertEqual(
            AttendanceRecord.objects.filter(employee=self.employee, is_manual=False).count(),
            1,
        )