from django.test import TestCase, Client

from account.models import UserAccount, Employee, Department
from hr.models import Company, OfficeQRPoint


def make_setup():
    company = Company.objects.create(name='Office QR Admin Co', bin_number='987654321098')
    dept = Department.objects.create(name='Office QR Admin Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_oqra', password='pass', role='administrator')
    hr_user = UserAccount.objects.create_user(username='hr_oqra', password='pass', role='hr')
    staff_user = UserAccount.objects.create_user(username='staff_oqra', password='pass', role='staff')
    Employee.objects.create(user=staff_user, department=dept, status='active')
    return admin, hr_user, staff_user


class OfficeQrAdminAccessTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, self.hr_user, self.staff_user = make_setup()

    def test_admin_can_open_page(self):
        self.client.login(username='admin_oqra', password='pass')
        r = self.client.get('/hr/attendance/office-qr/')
        self.assertEqual(r.status_code, 200)

    def test_hr_can_open_page(self):
        self.client.login(username='hr_oqra', password='pass')
        r = self.client.get('/hr/attendance/office-qr/')
        self.assertEqual(r.status_code, 200)

    def test_staff_forbidden(self):
        self.client.login(username='staff_oqra', password='pass')
        r = self.client.get('/hr/attendance/office-qr/')
        self.assertEqual(r.status_code, 403)

    def test_anonymous_redirected(self):
        r = self.client.get('/hr/attendance/office-qr/')
        self.assertIn(r.status_code, (302, 403))

    def test_reissue_requires_hr_journal(self):
        self.client.login(username='staff_oqra', password='pass')
        r = self.client.post('/hr/attendance/office-qr/reissue/')
        self.assertEqual(r.status_code, 403)

    def test_reissue_rejects_get(self):
        self.client.login(username='admin_oqra', password='pass')
        r = self.client.get('/hr/attendance/office-qr/reissue/')
        self.assertEqual(r.status_code, 405)

    def test_pdf_requires_hr_journal(self):
        self.client.login(username='staff_oqra', password='pass')
        r = self.client.get('/hr/attendance/office-qr/label/')
        self.assertEqual(r.status_code, 403)


class OfficeQrAdminBehaviorTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, self.hr_user, self.staff_user = make_setup()
        self.client.login(username='admin_oqra', password='pass')

    def test_admin_page_auto_creates_singleton_point(self):
        self.assertEqual(OfficeQRPoint.objects.count(), 0)
        self.client.get('/hr/attendance/office-qr/')
        self.assertEqual(OfficeQRPoint.objects.count(), 1)

    def test_admin_page_does_not_duplicate_point(self):
        self.client.get('/hr/attendance/office-qr/')
        self.client.get('/hr/attendance/office-qr/')
        self.assertEqual(OfficeQRPoint.objects.count(), 1)

    def test_admin_page_shows_scan_url(self):
        self.client.get('/hr/attendance/office-qr/')
        point = OfficeQRPoint.objects.first()
        r = self.client.get('/hr/attendance/office-qr/')
        self.assertContains(r, f'/hr/attendance/office-qr/{point.public_id}/')

    def test_reissue_changes_public_id(self):
        self.client.get('/hr/attendance/office-qr/')
        point = OfficeQRPoint.objects.first()
        old_id = point.public_id
        r = self.client.post('/hr/attendance/office-qr/reissue/')
        self.assertEqual(r.status_code, 302)
        point.refresh_from_db()
        self.assertNotEqual(point.public_id, old_id)

    def test_reissue_invalidates_old_public_id(self):
        self.client.get('/hr/attendance/office-qr/')
        point = OfficeQRPoint.objects.first()
        old_id = point.public_id
        self.client.post('/hr/attendance/office-qr/reissue/')
        r = self.client.get(f'/hr/attendance/office-qr/{old_id}/')
        self.assertEqual(r.status_code, 404)

    def test_label_pdf_returns_pdf(self):
        r = self.client.get('/hr/attendance/office-qr/label/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')

    def test_label_pdf_does_not_create_extra_point(self):
        self.client.get('/hr/attendance/office-qr/label/')
        self.assertEqual(OfficeQRPoint.objects.count(), 1)


class OfficeQrKioskRemovedTest(TestCase):
    """Динамическая QR-панель (kiosk) убрана — старые URL больше не должны резолвиться."""

    def setUp(self):
        self.client = Client()
        self.admin, self.hr_user, self.staff_user = make_setup()
        self.client.login(username='admin_oqra', password='pass')

    def test_checkin_page_has_no_dynamic_qr_panel(self):
        r = self.client.get('/hr/attendance/checkin/')
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'dynamicQrPanel')

    def test_old_kiosk_url_gone(self):
        r = self.client.get('/hr/attendance/kiosk/1/')
        self.assertEqual(r.status_code, 404)

    def test_old_qr_points_list_url_gone(self):
        r = self.client.get('/hr/attendance/qr-points/')
        self.assertEqual(r.status_code, 404)
