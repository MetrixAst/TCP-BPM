from django.test import TestCase

from account.models import UserAccount, Employee, Department
from hr.models import Company


def make_user(username, role='staff'):
    return UserAccount.objects.create_user(username=username, password='pass', role=role)


class AttendanceRegistryViewTest(TestCase):
    """Право на страницу /hr/attendance/registry/ (сами данные — на стороне DRF, см. hr/tests_attendance_registry.py)."""

    def setUp(self):
        self.admin = make_user('admin_ar_view', role='administrator')
        self.hr = make_user('hr_ar_view', role='hr')
        self.owner = make_user('owner_ar_view', role='owner')
        self.staff = make_user('staff_ar_view', role='staff')
        self.head_user = make_user('head_ar_view', role='staff')

        company = Company.objects.create(name='AR View Co', bin_number='222444666888')
        dept = Department.objects.create(name='AR View Dept', company=company)
        Employee.objects.create(user=self.staff, department=dept, status='active')
        Employee.objects.create(user=self.head_user, department=dept, status='active', head=True)

    def test_admin_can_open_page(self):
        self.client.force_login(self.admin)
        response = self.client.get('/hr/attendance/registry/')
        self.assertEqual(response.status_code, 200)

    def test_hr_can_open_page(self):
        self.client.force_login(self.hr)
        response = self.client.get('/hr/attendance/registry/')
        self.assertEqual(response.status_code, 200)

    def test_owner_can_open_page(self):
        self.client.force_login(self.owner)
        response = self.client.get('/hr/attendance/registry/')
        self.assertEqual(response.status_code, 200)

    def test_department_head_can_open_page(self):
        self.client.force_login(self.head_user)
        response = self.client.get('/hr/attendance/registry/')
        self.assertEqual(response.status_code, 200)

    def test_regular_staff_cannot_open_page(self):
        self.client.force_login(self.staff)
        response = self.client.get('/hr/attendance/registry/')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get('/hr/attendance/registry/')
        self.assertEqual(response.status_code, 302)
