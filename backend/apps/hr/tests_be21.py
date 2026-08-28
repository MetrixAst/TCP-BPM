from django.test import TestCase
from django.utils import timezone
from datetime import date, timedelta
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company, AttendanceRecord, AttendanceManualReason
from hr.enums import CheckInEnum


def make_setup():
    company = Company.objects.create(name='BE21 Co', bin_number='321321321321')
    dept = Department.objects.create(name='BE21 Dept', company=company)
    hr_user = UserAccount.objects.create_user(username='hr_be21', password='pass', role='hr')
    emp_user = UserAccount.objects.create_user(username='emp_be21', password='pass', role='staff')
    employee = Employee.objects.create(user=emp_user, department=dept, status='active')
    reason = AttendanceManualReason.objects.create(code='be21_reason', label='BE21 основание')
    return hr_user, employee, reason


class AttendanceReportTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.hr, self.employee, self.reason = make_setup()
        self.client.force_authenticate(user=self.hr)
        today = date.today()
        base = timezone.make_aware(timezone.datetime(today.year, today.month, today.day, 9, 0))
        AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=self.employee,
                event_type=CheckInEnum.DAY_START,
                timestamp=base,
                is_manual=False,
            ),
            AttendanceRecord(
                employee=self.employee,
                event_type=CheckInEnum.DAY_END,
                timestamp=base + timedelta(hours=8),
                is_manual=False,
            ),
        ])

        # Создаём ручную отметку
        AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=self.employee,
                event_type=CheckInEnum.DAY_START,
                timestamp=base - timedelta(days=1),
                is_manual=True,
                manual_author=self.hr,
                manual_reason=self.reason,
                manual_comment='Тест BE21',
            ),
        ])

    def test_report_returns_data(self):
        r = self.client.get('/api/v1/hr/attendance/report/')
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.data), 0)

    def test_report_filter_by_employee(self):
        r = self.client.get(f'/api/v1/hr/attendance/report/?employee_id={self.employee.pk}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]['employee_id'], self.employee.pk)

    def test_report_shows_manual_and_auto(self):
        r = self.client.get(f'/api/v1/hr/attendance/report/?employee_id={self.employee.pk}')
        self.assertEqual(r.status_code, 200)
        data = r.data[0]
        self.assertGreater(data['manual_records'], 0)
        self.assertGreater(data['auto_records'], 0)

    def test_report_export_xlsx(self):
        r = self.client.get('/api/v1/hr/attendance/report/?export=xlsx')
        self.assertEqual(r.status_code, 200)
        self.assertIn(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            r['Content-Type']
        )

    def test_staff_cannot_access_report(self):
        staff = UserAccount.objects.create_user(username='staff_be21', password='pass', role='staff')
        self.client.force_authenticate(user=staff)
        r = self.client.get('/api/v1/hr/attendance/report/')
        self.assertEqual(r.status_code, 403)

    def test_report_filter_by_period(self):
        today = date.today()
        date_from = (today - timedelta(days=7)).isoformat()
        date_to = today.isoformat()
        r = self.client.get(f'/api/v1/hr/attendance/report/?date_from={date_from}&date_to={date_to}&employee_id={self.employee.pk}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[0]['period']['date_from'], date_from)
        self.assertEqual(r.data[0]['period']['date_to'], date_to)