from django.test import TestCase
from django.utils import timezone
from datetime import date, timedelta
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company, AttendanceRecord
from hr.enums import CheckInEnum


def make_setup():
    company = Company.objects.create(name='Registry Co', bin_number='111333555777')
    dept = Department.objects.create(name='Registry Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_reg', password='pass', role='administrator')
    hr_user = UserAccount.objects.create_user(username='hr_reg', password='pass', role='hr')
    owner = UserAccount.objects.create_user(username='owner_reg', password='pass', role='owner')
    staff = UserAccount.objects.create_user(username='staff_reg', password='pass', role='staff')
    head_user = UserAccount.objects.create_user(username='head_reg', password='pass', role='staff')

    emp_staff = Employee.objects.create(user=staff, department=dept, status='active')
    emp_head = Employee.objects.create(user=head_user, department=dept, status='active', head=True)

    return admin, hr_user, owner, staff, head_user, emp_staff, emp_head, dept


class AttendanceRegistryAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.hr, self.owner, self.staff, self.head_user, \
            self.emp_staff, self.emp_head, self.dept = make_setup()

        # Создаём тестовые отметки
        today = date.today()
        base = timezone.make_aware(timezone.datetime(today.year, today.month, today.day, 9, 0))
        AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=self.emp_staff,
                event_type=CheckInEnum.DAY_START,
                timestamp=base,
                source='face',
            ),
            AttendanceRecord(
                employee=self.emp_staff,
                event_type=CheckInEnum.DAY_END,
                timestamp=base + timedelta(hours=8),
                source='face',
            ),
        ])

    def test_admin_can_access_registry(self):
        self.client.force_authenticate(user=self.admin)
        r = self.client.get('/api/v1/hr/attendance/registry/')
        self.assertEqual(r.status_code, 200)

    def test_hr_can_access_registry(self):
        self.client.force_authenticate(user=self.hr)
        r = self.client.get('/api/v1/hr/attendance/registry/')
        self.assertEqual(r.status_code, 200)

    def test_owner_can_access_registry(self):
        self.client.force_authenticate(user=self.owner)
        r = self.client.get('/api/v1/hr/attendance/registry/')
        self.assertEqual(r.status_code, 200)

    def test_staff_cannot_access_registry(self):
        self.client.force_authenticate(user=self.staff)
        r = self.client.get('/api/v1/hr/attendance/registry/')
        self.assertEqual(r.status_code, 403)

    def test_registry_returns_correct_fields(self):
        self.client.force_authenticate(user=self.admin)
        today = date.today().isoformat()
        r = self.client.get(f'/api/v1/hr/attendance/registry/?date_from={today}&date_to={today}')
        self.assertEqual(r.status_code, 200)
        if r.data:
            row = r.data[0]
            self.assertIn('date', row)
            self.assertIn('employee_id', row)
            self.assertIn('employee_name', row)
            self.assertIn('department', row)
            self.assertIn('day_start', row)
            self.assertIn('day_end', row)
            self.assertIn('total_hours', row)
            self.assertIn('source', row)

    def test_registry_filter_by_employee(self):
        self.client.force_authenticate(user=self.admin)
        r = self.client.get(f'/api/v1/hr/attendance/registry/?employee_id={self.emp_staff.pk}')
        self.assertEqual(r.status_code, 200)
        for row in r.data:
            self.assertEqual(row['employee_id'], self.emp_staff.pk)

    def test_registry_filter_by_department(self):
        self.client.force_authenticate(user=self.admin)
        r = self.client.get(f'/api/v1/hr/attendance/registry/?department_id={self.dept.pk}')
        self.assertEqual(r.status_code, 200)

    def test_export_xlsx(self):
        self.client.force_authenticate(user=self.admin)
        r = self.client.get('/api/v1/hr/attendance/registry/?export=xlsx')
        self.assertEqual(r.status_code, 200)
        self.assertIn(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            r['Content-Type']
        )

    def test_birthday_not_required(self):
        from django.test import Client
        c = Client()
        c.login(username='admin_reg', password='pass')
        user_no_birthday = UserAccount.objects.create_user(
            username='no_birthday_user', password='pass', role='staff'
        )
        self.assertIsNone(user_no_birthday.birthday)


class HeadManagerACLTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.hr, self.owner, self.staff, self.head_user, \
            self.emp_staff, self.emp_head, self.dept = make_setup()

    def test_head_can_access_registry(self):
        self.client.force_authenticate(user=self.head_user)
        r = self.client.get('/api/v1/hr/attendance/registry/')
        self.assertEqual(r.status_code, 200)

    def test_head_sees_only_own_department(self):
        self.client.force_authenticate(user=self.head_user)
        r = self.client.get('/api/v1/hr/attendance/registry/')
        self.assertEqual(r.status_code, 200)
        for row in r.data:
            self.assertEqual(row['department'], self.dept.name)