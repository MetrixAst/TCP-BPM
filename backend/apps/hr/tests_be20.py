from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company, AttendanceRecord, AttendanceManualReason, AttendanceEditLog
from hr.enums import CheckInEnum


def make_setup():
    company = Company.objects.create(name='BE20 Co', bin_number='999111222333')
    dept = Department.objects.create(name='BE20 Dept', company=company)
    hr_user = UserAccount.objects.create_user(username='hr_be20', password='pass', role='hr')
    admin_user = UserAccount.objects.create_user(username='admin_be20', password='pass', role='administrator')
    staff_user = UserAccount.objects.create_user(username='staff_be20', password='pass', role='staff')
    emp_user = UserAccount.objects.create_user(username='emp_be20', password='pass', role='staff')
    employee = Employee.objects.create(user=emp_user, department=dept, status='active')
    reason = AttendanceManualReason.objects.create(code='be20_reason', label='BE20 основание')
    return hr_user, admin_user, staff_user, employee, reason


class ManualAttendanceCRUDTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.hr, self.admin, self.staff, self.employee, self.reason = make_setup()

    def test_hr_can_create_manual_record(self):
        self.client.force_authenticate(user=self.hr)
        r = self.client.post('/api/v1/hr/attendance/manual/', {
            'employee': self.employee.pk,
            'event_type': 'day_start',
            'timestamp': timezone.now().isoformat(),
            'manual_reason': self.reason.pk,
            'manual_comment': 'Тест создания',
        }, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(AttendanceRecord.objects.filter(is_manual=True).exists())

    def test_staff_cannot_create_manual_record(self):
        self.client.force_authenticate(user=self.staff)
        r = self.client.post('/api/v1/hr/attendance/manual/', {
            'employee': self.employee.pk,
            'event_type': 'day_start',
            'timestamp': timezone.now().isoformat(),
        }, format='json')
        self.assertEqual(r.status_code, 403)

    def test_future_timestamp_rejected(self):
        self.client.force_authenticate(user=self.hr)
        r = self.client.post('/api/v1/hr/attendance/manual/', {
            'employee': self.employee.pk,
            'event_type': 'day_start',
            'timestamp': (timezone.now() + timedelta(days=1)).isoformat(),
            'manual_reason': self.reason.pk,
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_old_record_rejected(self):
        self.client.force_authenticate(user=self.hr)
        r = self.client.post('/api/v1/hr/attendance/manual/', {
            'employee': self.employee.pk,
            'event_type': 'day_start',
            'timestamp': (timezone.now() - timedelta(days=31)).isoformat(),
            'manual_reason': self.reason.pk,
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_duplicate_rejected(self):
        self.client.force_authenticate(user=self.hr)
        ts = timezone.now()
        self.client.post('/api/v1/hr/attendance/manual/', {
            'employee': self.employee.pk,
            'event_type': 'day_start',
            'timestamp': ts.isoformat(),
            'manual_reason': self.reason.pk,
        }, format='json')
        r = self.client.post('/api/v1/hr/attendance/manual/', {
            'employee': self.employee.pk,
            'event_type': 'day_start',
            'timestamp': ts.isoformat(),
            'manual_reason': self.reason.pk,
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_create_logs_history(self):
        self.client.force_authenticate(user=self.hr)
        self.client.post('/api/v1/hr/attendance/manual/', {
            'employee': self.employee.pk,
            'event_type': 'day_start',
            'timestamp': timezone.now().isoformat(),
            'manual_reason': self.reason.pk,
            'manual_comment': 'Тест лога',
        }, format='json')
        log = AttendanceEditLog.objects.filter(action='create').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.hr)
        self.assertIsNone(log.before)
        self.assertIsNotNone(log.after)

    def test_delete_logs_history(self):
        self.client.force_authenticate(user=self.hr)
        r = self.client.post('/api/v1/hr/attendance/manual/', {
            'employee': self.employee.pk,
            'event_type': 'day_end',
            'timestamp': timezone.now().isoformat(),
            'manual_reason': self.reason.pk,
        }, format='json')
        record_id = r.data['id']
        self.client.delete(f'/api/v1/hr/attendance/manual/{record_id}/')
        log = AttendanceEditLog.objects.filter(action='delete').first()
        self.assertIsNotNone(log)
        self.assertIsNotNone(log.before)
        self.assertIsNone(log.after)