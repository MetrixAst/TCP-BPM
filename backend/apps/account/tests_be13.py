from django.test import TestCase
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company


def make_dept():
    company = Company.objects.create(name='BE13 Co', bin_number='111222333444')
    return Department.objects.create(name='BE13 Dept', company=company)


def make_user(username):
    return UserAccount.objects.create_user(username=username, password='pass', role='staff')


class IINValidationModelTest(TestCase):

    def setUp(self):
        self.dept = make_dept()

    def test_empty_iin_allowed(self):
        user = make_user('emp_no_iin')
        emp = Employee(user=user, department=self.dept, iin=None)
        emp.full_clean()  
        emp.save()
        self.assertIsNone(emp.iin)

    def test_blank_iin_allowed(self):
        user = make_user('emp_blank_iin')
        emp = Employee(user=user, department=self.dept, iin='')
        emp.full_clean()
        emp.save()

    def test_valid_iin_accepted(self):
        user = make_user('emp_valid_iin')
        emp = Employee(user=user, department=self.dept, iin='123456789012')
        emp.full_clean()
        emp.save()
        self.assertEqual(emp.iin, '123456789012')

    def test_invalid_iin_format_rejected(self):
        user = make_user('emp_bad_iin')
        emp = Employee(user=user, department=self.dept, iin='12345')
        with self.assertRaises(ValidationError):
            emp.full_clean()

    def test_non_digit_iin_rejected(self):
        user = make_user('emp_alpha_iin')
        emp = Employee(user=user, department=self.dept, iin='12345678901a')
        with self.assertRaises(ValidationError):
            emp.full_clean()

    def test_duplicate_iin_rejected(self):
        user1 = make_user('emp_iin_1')
        emp1 = Employee(user=user1, department=self.dept, iin='123456789012')
        emp1.save()

        user2 = make_user('emp_iin_2')
        emp2 = Employee(user=user2, department=self.dept, iin='123456789012')
        with self.assertRaises(ValidationError):
            emp2.full_clean()

    def test_multiple_employees_without_iin(self):
        """Несколько сотрудников без ИИН — не должно быть конфликта уникальности."""
        user1 = make_user('emp_null_1')
        user2 = make_user('emp_null_2')
        emp1 = Employee(user=user1, department=self.dept, iin=None)
        emp1.save()
        emp2 = Employee(user=user2, department=self.dept, iin=None)
        emp2.save()
        self.assertEqual(Employee.objects.filter(iin__isnull=True).count(), 2)


class IINValidationAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = UserAccount.objects.create_user(
            username='admin_be13', password='pass', role='administrator'
        )
        self.client.force_authenticate(user=self.admin)
        self.dept = make_dept()

    def test_api_employee_without_iin(self):
        r = self.client.get('/api/v1/hr/employees/')
        self.assertEqual(r.status_code, 200)

    def test_serializer_invalid_iin(self):
        from hr.serializers import EmployeeSerializer
        user = make_user('ser_test')
        emp = Employee.objects.create(user=user, department=self.dept)
        s = EmployeeSerializer(emp, data={'iin': '123'}, partial=True)
        self.assertFalse(s.is_valid())
        self.assertIn('iin', s.errors)

    def test_serializer_valid_iin(self):
        from hr.serializers import EmployeeSerializer
        user = make_user('ser_test2')
        emp = Employee.objects.create(user=user, department=self.dept)
        s = EmployeeSerializer(emp, data={'iin': '123456789012'}, partial=True)
        self.assertTrue(s.is_valid())

    def test_serializer_empty_iin(self):
        from hr.serializers import EmployeeSerializer
        user = make_user('ser_test3')
        emp = Employee.objects.create(user=user, department=self.dept)
        s = EmployeeSerializer(emp, data={'iin': ''}, partial=True)
        self.assertTrue(s.is_valid())