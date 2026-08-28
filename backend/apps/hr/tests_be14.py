from django.test import TestCase
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department, EmployeeStatusLog
from hr.models import Company


def make_dept():
    company = Company.objects.create(name='BE14 Co', bin_number='444555666777')
    return Department.objects.create(name='BE14 Dept', company=company)


def make_user(username, role='staff'):
    return UserAccount.objects.create_user(username=username, password='pass', role=role)


def make_employee(username, dept):
    user = make_user(username)
    return Employee.objects.create(user=user, department=dept, status='active')


class DeactivateAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_be14', role='administrator')
        self.client.force_authenticate(user=self.admin)
        self.dept = make_dept()
        self.employee = make_employee('emp_be14', self.dept)

    def test_deactivate_requires_reason(self):
        r = self.client.post(f'/api/v1/hr/employees/{self.employee.pk}/deactivate/', {'reason': 'ок'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_deactivate_with_valid_reason(self):
        r = self.client.post(f'/api/v1/hr/employees/{self.employee.pk}/deactivate/', {'reason': 'причина увольнения'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, 'dismissed')

    def test_deactivate_creates_audit_log(self):
        self.client.post(f'/api/v1/hr/employees/{self.employee.pk}/deactivate/', {'reason': 'причина увольнения'}, format='json')
        log = EmployeeStatusLog.objects.filter(employee=self.employee).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.old_status, 'active')
        self.assertEqual(log.new_status, 'dismissed')
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.reason, 'причина увольнения')


class ActivateAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_be14_act', role='administrator')
        self.client.force_authenticate(user=self.admin)
        self.dept = make_dept()
        self.employee = make_employee('emp_be14_act', self.dept)
        self.employee.status = 'dismissed'
        self.employee.save()

    def test_activate_employee(self):
        r = self.client.post(f'/api/v1/hr/employees/{self.employee.pk}/activate/', {}, format='json')
        self.assertEqual(r.status_code, 200)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, 'active')

    def test_activate_creates_audit_log(self):
        self.client.post(f'/api/v1/hr/employees/{self.employee.pk}/activate/', {}, format='json')
        log = EmployeeStatusLog.objects.filter(employee=self.employee).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.old_status, 'dismissed')
        self.assertEqual(log.new_status, 'active')
        self.assertEqual(log.actor, self.admin)


class BatchStatusAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_be14_batch', role='administrator')
        self.client.force_authenticate(user=self.admin)
        self.dept = make_dept()
        self.emp1 = make_employee('emp_batch_1', self.dept)
        self.emp2 = make_employee('emp_batch_2', self.dept)

    def test_batch_deactivate_requires_reason(self):
        r = self.client.post('/api/v1/hr/employees/batch-status/', {
            'employee_ids': [self.emp1.pk, self.emp2.pk],
            'action': 'deactivate',
            'reason': 'ок',
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_batch_deactivate(self):
        r = self.client.post('/api/v1/hr/employees/batch-status/', {
            'employee_ids': [self.emp1.pk, self.emp2.pk],
            'action': 'deactivate',
            'reason': 'массовое увольнение',
        }, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['updated'], 2)
        self.emp1.refresh_from_db()
        self.emp2.refresh_from_db()
        self.assertEqual(self.emp1.status, 'dismissed')
        self.assertEqual(self.emp2.status, 'dismissed')

    def test_batch_activate(self):
        self.emp1.status = 'dismissed'
        self.emp1.save()
        self.emp2.status = 'dismissed'
        self.emp2.save()
        r = self.client.post('/api/v1/hr/employees/batch-status/', {
            'employee_ids': [self.emp1.pk, self.emp2.pk],
            'action': 'activate',
            'reason': '',
        }, format='json')
        self.assertEqual(r.status_code, 200)
        self.emp1.refresh_from_db()
        self.emp2.refresh_from_db()
        self.assertEqual(self.emp1.status, 'active')
        self.assertEqual(self.emp2.status, 'active')

    def test_batch_creates_audit_logs(self):
        self.client.post('/api/v1/hr/employees/batch-status/', {
            'employee_ids': [self.emp1.pk, self.emp2.pk],
            'action': 'deactivate',
            'reason': 'массовое увольнение',
        }, format='json')
        logs = EmployeeStatusLog.objects.filter(employee__in=[self.emp1, self.emp2])
        self.assertEqual(logs.count(), 2)

    def test_invalid_action(self):
        r = self.client.post('/api/v1/hr/employees/batch-status/', {
            'employee_ids': [self.emp1.pk],
            'action': 'unknown',
            'reason': 'тест',
        }, format='json')
        self.assertEqual(r.status_code, 400)