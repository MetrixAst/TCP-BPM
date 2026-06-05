from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from account.models import Department, UserAccount
from account.role_permissions import RoleEnums
from audit.models import AuditLog
from hr.models import Company


class DepartmentOrgApiTest(TestCase):
    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            username='org_api_admin',
            password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.staff = UserAccount.objects.create_user(
            username='org_api_staff',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        self.company = Company.objects.create(name='Org Test Co', bin_number='123456789012')
        self.client = APIClient()

    def test_create_department_logs_audit(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('department-list')
        response = self.client.post(url, {
            'name': 'Новый отдел',
            'company': self.company.pk,
            'parent': None,
            'level_type': 'department',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        dept = Department.objects.get(name='Новый отдел')
        self.assertTrue(
            AuditLog.objects.filter(
                object_type='Department',
                object_id=str(dept.pk),
                action=AuditLog.Action.CREATE,
            ).exists()
        )

    def test_move_department_parent(self):
        self.client.force_authenticate(user=self.admin)
        parent = Department.objects.create(name='Родитель', company=self.company)
        child = Department.objects.create(name='Дочерний', company=self.company, parent=parent)

        url = reverse('department-detail', kwargs={'pk': child.pk})
        response = self.client.patch(url, {'parent': None}, format='json')
        self.assertEqual(response.status_code, 200)
        child.refresh_from_db()
        self.assertIsNone(child.parent_id)

    def test_delete_department_with_employees_forbidden(self):
        from account.models import Employee
        from hr.enums import EmployeeStatusEnum
        from hr.models import Position

        self.client.force_authenticate(user=self.admin)
        dept = Department.objects.create(name='С сотрудниками', company=self.company)
        position = Position.objects.create(title='Dev', department=dept)
        user = UserAccount.objects.create_user(
            username='org_emp',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        Employee.objects.create(
            user=user,
            department=dept,
            position=position,
            status=EmployeeStatusEnum.ACTIVE,
        )

        url = reverse('department-detail', kwargs={'pk': dept.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Department.objects.filter(pk=dept.pk).exists())

    def test_staff_cannot_create_department(self):
        self.client.force_authenticate(user=self.staff)
        url = reverse('department-list')
        response = self.client.post(url, {
            'name': 'Запрещено',
            'company': self.company.pk,
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_tree_endpoint(self):
        Department.objects.create(name='A', company=self.company)
        self.client.force_authenticate(user=self.admin)
        url = reverse('department-tree')
        response = self.client.get(url, {'company': self.company.pk})
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()), 1)
