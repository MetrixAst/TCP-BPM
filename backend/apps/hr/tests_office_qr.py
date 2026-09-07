from django.test import TestCase, Client
from django.utils import timezone
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company, AttendanceRecord, OfficeQRPoint
from hr.enums import CheckInEnum


def make_setup():
    company = Company.objects.create(name='Office QR Co', bin_number='123456789013')
    dept = Department.objects.create(name='Office QR Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_oqr', password='pass', role='administrator')
    emp_user = UserAccount.objects.create_user(username='emp_oqr', password='pass', role='staff')
    employee = Employee.objects.create(user=emp_user, department=dept, status='active')
    point = OfficeQRPoint.objects.create(name='Главный вход', created_by=admin)
    return admin, emp_user, employee, point


class OfficeQRPointModelTest(TestCase):

    def setUp(self):
        self.admin, self.emp_user, self.emp, self.point = make_setup()

    def test_point_has_public_id(self):
        self.assertIsNotNone(self.point.public_id)

    def test_reissue_changes_public_id(self):
        old_id = self.point.public_id
        self.point.reissue()
        self.assertNotEqual(self.point.public_id, old_id)

    def test_point_is_active_by_default(self):
        self.assertTrue(self.point.is_active)


class OfficeQRPreviewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, self.emp_user, self.emp, self.point = make_setup()
        self.client.login(username='emp_oqr', password='pass')

    def test_get_returns_200(self):
        r = self.client.get(f'/hr/attendance/office-qr/{self.point.public_id}/')
        self.assertEqual(r.status_code, 200)

    def test_get_does_not_create_record(self):
        count_before = AttendanceRecord.objects.count()
        self.client.get(f'/hr/attendance/office-qr/{self.point.public_id}/')
        self.assertEqual(AttendanceRecord.objects.count(), count_before)

    def test_inactive_point_returns_404(self):
        self.point.is_active = False
        self.point.save()
        r = self.client.get(f'/hr/attendance/office-qr/{self.point.public_id}/')
        self.assertEqual(r.status_code, 404)

    def test_unauthenticated_redirects(self):
        self.client.logout()
        r = self.client.get(f'/hr/attendance/office-qr/{self.point.public_id}/')
        self.assertIn(r.status_code, [302, 403])


class OfficeQRCheckinTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, self.emp_user, self.emp, self.point = make_setup()
        self.client.login(username='emp_oqr', password='pass')

    def test_post_creates_day_start(self):
        r = self.client.post(f'/hr/attendance/office-qr/{self.point.public_id}/checkin/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['success'])
        self.assertTrue(AttendanceRecord.objects.filter(
            employee=self.emp,
            event_type=CheckInEnum.DAY_START,
            source='qr',
        ).exists())

    def test_second_post_creates_day_end(self):
        AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=self.emp,
                event_type=CheckInEnum.DAY_START,
                timestamp=timezone.now(),
                source='qr',
            )
        ])
        r = self.client.post(f'/hr/attendance/office-qr/{self.point.public_id}/checkin/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(AttendanceRecord.objects.filter(
            employee=self.emp,
            event_type=CheckInEnum.DAY_END,
        ).exists())

    def test_idempotency_no_duplicate(self):
        AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=self.emp,
                event_type=CheckInEnum.DAY_START,
                timestamp=timezone.now(),
                source='qr',
            ),
            AttendanceRecord(
                employee=self.emp,
                event_type=CheckInEnum.DAY_END,
                timestamp=timezone.now(),
                source='qr',
            ),
        ])
        count_before = AttendanceRecord.objects.count()
        r = self.client.post(f'/hr/attendance/office-qr/{self.point.public_id}/checkin/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['already_done'])
        self.assertEqual(AttendanceRecord.objects.count(), count_before)

    def test_source_is_qr(self):
        self.client.post(f'/hr/attendance/office-qr/{self.point.public_id}/checkin/')
        record = AttendanceRecord.objects.filter(employee=self.emp).first()
        self.assertEqual(record.source, 'qr')

    def test_get_not_allowed_for_checkin(self):
        r = self.client.get(f'/hr/attendance/office-qr/{self.point.public_id}/checkin/')
        self.assertEqual(r.status_code, 405)

    def test_historical_data_preserved(self):
        AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=self.emp,
                event_type=CheckInEnum.DAY_START,
                timestamp=timezone.now() - timezone.timedelta(days=5),
                source='face',
            )
        ])
        self.client.post(f'/hr/attendance/office-qr/{self.point.public_id}/checkin/')
        self.assertTrue(AttendanceRecord.objects.filter(
            employee=self.emp, source='face'
        ).exists())