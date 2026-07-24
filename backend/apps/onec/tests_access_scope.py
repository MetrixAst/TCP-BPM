from django.http import Http404
from django.test import TestCase
from django.urls import reverse

from account.models import AccessScope, Department, Employee, UserAccount
from account.role_permissions import RoleEnums
from hr.enums import EmployeeStatusEnum
from hr.models import Company, Position
from onec.models import Counterparty, CounterpartyType


class CounterpartyAccessScopeTest(TestCase):
    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            username='acl_admin',
            password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.staff = UserAccount.objects.create_user(
            username='acl_staff',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        company = Company.objects.create(name='ACL Co')
        self.department = Department.objects.create(name='Finance', company=company)
        position = Position.objects.create(title='Analyst', department=self.department)
        Employee.objects.create(
            user=self.staff,
            department=self.department,
            position=position,
            status=EmployeeStatusEnum.ACTIVE,
        )

        self.public_cp = Counterparty.objects.create(
            id_1c='ACL-PUBLIC',
            full_name='Public CP',
            short_name='Public',
        )
        scope = AccessScope.objects.create(name='Finance only', roles=[RoleEnums.STAFF.value])
        scope.departments.add(self.department)
        self.restricted_type = CounterpartyType.objects.create(
            name='Finance vendors',
            code='finance_vendors',
            access_scope=scope,
        )
        self.restricted_cp = Counterparty.objects.create(
            id_1c='ACL-RESTRICTED',
            full_name='Restricted CP',
            short_name='Restricted',
            counterparty_type=self.restricted_type,
        )
        other_scope = AccessScope.objects.create(
            name='HR only',
            roles=[RoleEnums.HR.value],
        )
        other_type = CounterpartyType.objects.create(
            name='HR vendors',
            code='hr_vendors',
            access_scope=other_scope,
        )
        self.hidden_cp = Counterparty.objects.create(
            id_1c='ACL-HIDDEN',
            full_name='Hidden CP',
            short_name='Hidden',
            counterparty_type=other_type,
        )

    def test_staff_sees_public_and_department_scoped(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('onec:counterparty_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Public')
        self.assertContains(response, 'Restricted')
        self.assertNotContains(response, 'Hidden')

    def test_staff_cannot_open_hidden_detail(self):
        from account.services.access_scope import (
            _allowed_counterparty_type_ids,
            filter_counterparties_queryset,
            user_can_view_counterparty,
        )

        self.assertFalse(user_can_view_counterparty(self.staff, self.hidden_cp))
        self.assertFalse(
            filter_counterparties_queryset(
                Counterparty.objects.filter(pk=self.hidden_cp.pk),
                self.staff,
            ).exists()
        )
        self.assertTrue(self.client.login(username='acl_staff', password='pass'))
        url = reverse('onec:counterparty_detail', kwargs={'pk': self.hidden_cp.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_search_api_respects_acl(self):
        self.client.force_login(self.staff)
        url = reverse('onec:counterparty_search_api')
        data = self.client.get(f'{url}?q=Hidden').json()
        self.assertEqual(data['results'], [])
        data_ok = self.client.get(f'{url}?q=Restricted').json()
        self.assertEqual(len(data_ok['results']), 1)

    def test_admin_sees_all(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('onec:counterparty_list'))
        self.assertContains(response, 'Hidden')
        self.assertContains(response, 'Restricted')

    def test_type_settings_requires_admin(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse('onec:counterparty_type_list')).status_code,
            403,
        )
