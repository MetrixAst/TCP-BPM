from rest_framework import status
from rest_framework.test import APITestCase
from django.urls import reverse

from account.models import UserAccount, Employee, Department
from account.role_permissions import RoleEnums
from hr.models import Company


class HrAPITestCase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name='API Corp', bin_number='123456789012')
        self.dept = Department.objects.create(name='IT', company=self.company)
        self.hr_admin = UserAccount.objects.create_user(
            username='hr_admin',
            password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.staff_user = UserAccount.objects.create_user(
            username='hr_staff',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        self.guest = UserAccount.objects.create_user(
            username='hr_guest',
            password='pass',
            role=RoleEnums.GUEST.value,
        )
        self.emp_user = UserAccount.objects.create_user(
            username='emp_api',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        self.employee = Employee.objects.create(
            user=self.emp_user,
            department=self.dept,
            iin='990101300123',
        )
        self.companies_url = reverse('company-list')
        self.employees_url = reverse('employee-list')
        self.departments_url = reverse('department-list')

    def test_companies_list_unauthenticated_401(self):
        response = self.client.get(self.companies_url)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_companies_list_guest_403(self):
        self.client.force_authenticate(user=self.guest)
        self.assertEqual(
            self.client.get(self.companies_url).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_companies_list_staff_read_200(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self.companies_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data['count'], 1)

    def test_company_create_admin_201(self):
        self.client.force_authenticate(user=self.hr_admin)
        response = self.client.post(
            self.companies_url,
            {'name': 'New Co', 'bin_number': '987654321098'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_company_create_staff_403(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(
            self.companies_url,
            {'name': 'Blocked Co', 'bin_number': '111111111111'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_retrieve(self):
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('employee-detail', kwargs={'pk': self.employee.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'emp_api')

    def test_departments_list(self):
        self.client.force_authenticate(user=self.hr_admin)
        response = self.client.get(self.departments_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
