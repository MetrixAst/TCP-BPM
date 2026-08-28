from django.test import TestCase, RequestFactory
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company, QRPoint, QRToken, QRScanAudit, AttendanceRecord
from hr.enums import CheckInEnum


def make_setup():
    company = Company.objects.create(name='QR Co', bin_number='111222333444')
    dept = Department.objects.create(name='QR Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_qr', password='pass', role='administrator')
    emp_user = UserAccount.objects.create_user(username='emp_qr', password='pass', role='staff')
    employee = Employee.objects.create(user=emp_user, department=dept, status='active')
    point = QRPoint.objects.create(name='Главный вход', location='Lobby', created_by=admin)
    return admin, emp_user, employee, point


def make_token(point, event_type='day_start', expired=False, ttl=45):
    import secrets
    expires_at = timezone.now() - timedelta(seconds=1) if expired else timezone.now() + timedelta(seconds=ttl)
    return QRToken.objects.create(
        token=secrets.token_urlsafe(32),
        qr_point=point,
        event_type=event_type,
        expires_at=expires_at,
    )


class QRTokenModelTest(TestCase):

    def setUp(self):
        self.admin, self.emp_user, self.employee, self.point = make_setup()

    def test_token_not_expired(self):
        token = make_token(self.point)
        self.assertFalse(token.is_expired)

    def test_token_expired(self):
        token = make_token(self.point, expired=True)
        self.assertTrue(token.is_expired)

    def test_token_not_used_by_user(self):
        token = make_token(self.point)
        self.assertFalse(token.is_used_by(self.emp_user))

    def test_token_used_by_user(self):
        token = make_token(self.point)
        token.used_by.add(self.emp_user)
        self.assertTrue(token.is_used_by(self.emp_user))

    def test_multiple_users_same_token(self):
        token = make_token(self.point)
        user2 = UserAccount.objects.create_user(username='emp_qr2', password='pass', role='staff')
        token.used_by.add(self.emp_user)
        token.used_by.add(user2)
        self.assertTrue(token.is_used_by(self.emp_user))
        self.assertTrue(token.is_used_by(user2))


class QRCheckinWebTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.emp_user, self.employee, self.point = make_setup()
        self.client.force_login(self.emp_user)

    def test_valid_token_creates_attendance(self):
        token = make_token(self.point)
        r = self.client.post('/hr/attendance/qr-checkin/', {'token': token.token})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['success'])
        self.assertTrue(AttendanceRecord.objects.filter(
            employee=self.employee, source='qr'
        ).exists())

    def test_expired_token_returns_410(self):
        token = make_token(self.point, expired=True)
        r = self.client.post('/hr/attendance/qr-checkin/', {'token': token.token})
        self.assertEqual(r.status_code, 410)

    def test_invalid_token_returns_400(self):
        r = self.client.post('/hr/attendance/qr-checkin/', {'token': 'invalid_token_xxx'})
        self.assertEqual(r.status_code, 400)

    def test_replay_returns_409(self):
        token = make_token(self.point)
        token.used_by.add(self.emp_user)
        r = self.client.post('/hr/attendance/qr-checkin/', {'token': token.token})
        self.assertEqual(r.status_code, 409)

    def test_no_employee_profile_returns_403(self):
        user_no_emp = UserAccount.objects.create_user(
            username='no_emp_qr', password='pass', role='staff'
        )
        self.client.force_login(user_no_emp)
        token = make_token(self.point)
        r = self.client.post('/hr/attendance/qr-checkin/', {'token': token.token})
        self.assertEqual(r.status_code, 403)

    def test_audit_created_on_success(self):
        token = make_token(self.point)
        self.client.post('/hr/attendance/qr-checkin/', {'token': token.token})
        self.assertTrue(QRScanAudit.objects.filter(
            action=QRScanAudit.ACTION_SUCCESS,
            user=self.emp_user,
        ).exists())

    def test_audit_created_on_expired(self):
        token = make_token(self.point, expired=True)
        self.client.post('/hr/attendance/qr-checkin/', {'token': token.token})
        self.assertTrue(QRScanAudit.objects.filter(
            action=QRScanAudit.ACTION_EXPIRED,
        ).exists())

    def test_audit_created_on_replay(self):
        token = make_token(self.point)
        token.used_by.add(self.emp_user)
        self.client.post('/hr/attendance/qr-checkin/', {'token': token.token})
        self.assertTrue(QRScanAudit.objects.filter(
            action=QRScanAudit.ACTION_REPLAY,
        ).exists())

    def test_source_is_qr(self):
        token = make_token(self.point)
        self.client.post('/hr/attendance/qr-checkin/', {'token': token.token})
        record = AttendanceRecord.objects.filter(employee=self.employee).first()
        self.assertEqual(record.source, 'qr')

    def test_historical_face_records_preserved(self):
        """Старые Face отметки не затрагиваются."""
        AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=self.employee,
                event_type=CheckInEnum.DAY_START,
                timestamp=timezone.now() - timedelta(days=30),
                source='face',
            )
        ])
        token = make_token(self.point, event_type='day_end')
        self.client.post('/hr/attendance/qr-checkin/', {'token': token.token})
        self.assertTrue(AttendanceRecord.objects.filter(
            employee=self.employee, source='face'
        ).exists())


class QRKioskTokenTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.emp_user, self.employee, self.point = make_setup()
        self.client.force_login(self.admin)

    def test_kiosk_token_generated(self):
        r = self.client.get(f'/hr/attendance/kiosk/{self.point.pk}/token/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn('token', data)
        self.assertIn('scan_url', data)
        self.assertIn('expires_in', data)
        self.assertEqual(data['expires_in'], 45)

    def test_kiosk_token_event_type(self):
        r = self.client.get(f'/hr/attendance/kiosk/{self.point.pk}/token/?event_type=day_end')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['event_type'], 'day_end')

    def test_inactive_point_returns_404(self):
        self.point.is_active = False
        self.point.save()
        r = self.client.get(f'/hr/attendance/kiosk/{self.point.pk}/token/')
        self.assertEqual(r.status_code, 404)