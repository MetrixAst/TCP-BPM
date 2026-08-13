from django.test import TestCase, RequestFactory
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from account.models_rbac import AppPermission, PermissionProfile, UserPermissionOverride, PermissionAuditLog
from hr.models import Company
from tasks.models import Task
from tickets.models import ServiceRequest


def make_company():
    return Company.objects.create(name='BE22 Co', bin_number='222333444555')


def make_dept(company):
    return Department.objects.create(name='BE22 Dept', company=company)


def make_user(username, role='staff'):
    return UserAccount.objects.create_user(username=username, password='pass', role=role)


def make_employee(user, dept, head=False):
    return Employee.objects.create(user=user, department=dept, head=head, status='active')


class RoleAccessSecurityTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.company = make_company()
        self.dept = make_dept(self.company)
        self.roles = {
            'administrator': make_user('admin_be22', 'administrator'),
            'hr': make_user('hr_be22', 'hr'),
            'staff': make_user('staff_be22', 'staff'),
            'guest': make_user('guest_be22', 'guest'),
            'tenant': make_user('tenant_be22', 'tenant'),
            'owner': make_user('owner_be22', 'owner'),
            'cfo': make_user('cfo_be22', 'cfo'),
            'chief_accountant': make_user('ca_be22', 'chief_accountant'),
        }

    def test_only_admin_can_access_permissions_catalog(self):
        self.client.force_authenticate(user=self.roles['administrator'])
        r = self.client.get('/api/v1/permissions/catalog/')
        self.assertEqual(r.status_code, 200)

        for role in ['hr', 'staff', 'guest', 'tenant']:
            self.client.force_authenticate(user=self.roles[role])
            r = self.client.get('/api/v1/permissions/catalog/')
            self.assertIn(r.status_code, [403, 401])

    def test_only_admin_can_access_audit_log(self):
        self.client.force_authenticate(user=self.roles['administrator'])
        r = self.client.get('/api/v1/permissions/audit/')
        self.assertEqual(r.status_code, 200)

        for role in ['hr', 'staff', 'guest', 'tenant']:
            self.client.force_authenticate(user=self.roles[role])
            r = self.client.get('/api/v1/permissions/audit/')
            self.assertIn(r.status_code, [403, 401])

    def test_only_hr_admin_can_access_manual_attendance(self):
        for role in ['administrator', 'hr']:
            self.client.force_authenticate(user=self.roles[role])
            r = self.client.get('/api/v1/hr/attendance/manual/')
            self.assertEqual(r.status_code, 200)

        for role in ['staff', 'guest', 'tenant']:
            self.client.force_authenticate(user=self.roles[role])
            r = self.client.get('/api/v1/hr/attendance/manual/')
            self.assertEqual(r.status_code, 403)


class DirectURLSecurityTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.company = make_company()
        self.dept = make_dept(self.company)
        self.staff = make_user('staff_url_be22', 'staff')
        make_employee(self.staff, self.dept)

    def test_task_delete_requires_author_or_admin(self):
        admin = make_user('admin_url_be22', 'administrator')
        task = Task.objects.create(
            author=admin,
            title='Test task BE22',
            deadline=timezone.now().date(),
            status='created',
        )
        self.client.force_authenticate(user=self.staff)
        r = self.client.delete(f'/api/v1/tasks/{task.pk}/', {'reason': 'причина удаления'}, format='json')
        self.assertIn(r.status_code, [403, 404])

    def test_pending_approval_hidden_from_staff(self):
        factory = RequestFactory()
        staff = make_user('staff_pending_be22', 'staff')
        make_employee(staff, self.dept)
        ticket = ServiceRequest.objects.create(
            author=staff,
            title='Test BE22',
            category='other',
            priority='medium',
            status='pending_approval',
        )
        request = factory.get('/')
        request.user = self.staff
        qs = ServiceRequest.get_available_queryset(request)
        self.assertNotIn(ticket, qs)


class AuditSecurityTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.company = make_company()
        self.dept = make_dept(self.company)
        self.admin = make_user('admin_audit_be22', 'administrator')
        self.staff = make_user('staff_audit_be22', 'staff')
        make_employee(self.staff, self.dept)
        self.client.force_authenticate(user=self.admin)

    def test_permission_override_creates_audit(self):
        perm = AppPermission.objects.get(code='dashboard')
        count_before = PermissionAuditLog.objects.count()
        UserPermissionOverride.objects.create(
            user=self.staff,
            permission=perm,
            effect='ALLOW',
            created_by=self.admin,
        )
        self.assertGreater(PermissionAuditLog.objects.count(), count_before)

    def test_employee_deactivation_creates_log(self):
        from account.models import EmployeeStatusLog
        emp = Employee.objects.filter(status='active').first()
        if not emp:
            emp = make_employee(self.staff, self.dept)
        count_before = EmployeeStatusLog.objects.count()
        self.client.post(
            f'/api/v1/hr/employees/{emp.pk}/deactivate/',
            {'reason': 'тест деактивации BE22'},
            format='json',
        )
        self.assertGreater(EmployeeStatusLog.objects.count(), count_before)


class BatchOperationsSecurityTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.company = make_company()
        self.dept = make_dept(self.company)
        self.admin = make_user('admin_batch_be22', 'administrator')
        self.client.force_authenticate(user=self.admin)

    def test_batch_deactivate_requires_reason(self):
        emp1 = make_employee(make_user('emp_batch1_be22'), self.dept)
        emp2 = make_employee(make_user('emp_batch2_be22'), self.dept)
        r = self.client.post('/api/v1/hr/employees/batch-status/', {
            'employee_ids': [emp1.pk, emp2.pk],
            'action': 'deactivate',
            'reason': 'ок',
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_batch_deactivate_logs_all(self):
        from account.models import EmployeeStatusLog
        emp1 = make_employee(make_user('emp_blog1_be22'), self.dept)
        emp2 = make_employee(make_user('emp_blog2_be22'), self.dept)
        count_before = EmployeeStatusLog.objects.count()
        self.client.post('/api/v1/hr/employees/batch-status/', {
            'employee_ids': [emp1.pk, emp2.pk],
            'action': 'deactivate',
            'reason': 'массовое тестирование BE22',
        }, format='json')
        self.assertEqual(EmployeeStatusLog.objects.count(), count_before + 2)


class HistoricalDataTest(TestCase):

    def test_soft_deleted_tasks_remain_in_db(self):
        admin = make_user('admin_hist_be22', 'administrator')
        task = Task.objects.create(
            author=admin,
            title='Historical task BE22',
            deadline=timezone.now().date(),
            status='created',
        )
        task.soft_delete(admin, reason='тест исторических данных')
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())
        self.assertTrue(Task.objects.get(pk=task.pk).is_deleted)

    def test_old_attendance_records_preserved(self):
        from hr.models import AttendanceRecord, AttendanceManualReason
        from hr.enums import CheckInEnum
        company = make_company()
        dept = make_dept(company)
        emp_user = make_user('emp_hist_be22')
        emp = make_employee(emp_user, dept)
        AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=emp,
                event_type=CheckInEnum.LUNCH_START,
                timestamp=timezone.now() - timedelta(days=60),
            )
        ])
        self.assertEqual(
            AttendanceRecord.objects.filter(
                employee=emp,
                event_type=CheckInEnum.LUNCH_START,
            ).count(),
            1,
        )

class PerformanceTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_perf_be22', 'administrator')
        self.client.force_authenticate(user=self.admin)

    def test_permissions_catalog_response_time(self):
        import time
        start = time.time()
        r = self.client.get('/api/v1/permissions/catalog/')
        elapsed = time.time() - start
        self.assertEqual(r.status_code, 200)
        self.assertLess(elapsed, 2.0, f'Слишком медленно: {elapsed:.2f}s')

    def test_attendance_report_response_time(self):
        import time
        start = time.time()
        r = self.client.get('/api/v1/hr/attendance/report/')
        elapsed = time.time() - start
        self.assertEqual(r.status_code, 200)
        self.assertLess(elapsed, 3.0, f'Слишком медленно: {elapsed:.2f}s')

    def test_employees_list_response_time(self):
        import time
        start = time.time()
        r = self.client.get('/api/v1/hr/employees/')
        elapsed = time.time() - start
        self.assertEqual(r.status_code, 200)
        self.assertLess(elapsed, 2.0, f'Слишком медленно: {elapsed:.2f}s')