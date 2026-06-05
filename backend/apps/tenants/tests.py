from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount
from account.role_permissions import RoleEnums
from tenants.models import Tenant, TenantCategory, Room


class TenantPortalAccessTest(TestCase):
    def setUp(self):
        self.room = Room.objects.create(number='301', map_id='r301', floor=3)
        self.category = TenantCategory.objects.create(title='Office')
        self.tenant = Tenant.objects.create(
            name='Acme', category=self.category, room=self.room,
            area=60, price=1500, phone='+77000000000', email='a@test.kz',
            address='Floor 3', contact='Boss',
            start_date='2025-01-01', end_date='2026-01-01',
            discount_date='2025-06-01', increase_type='percent',
        )
        self.staff = UserAccount.objects.create_user(
            username='staff_t', email='s@test.kz', password='pass',
            role=RoleEnums.STAFF.value,
        )

    def test_staff_can_issue_credentials(self):
        self.client.force_login(self.staff)
        resp = self.client.post(reverse('tenants:portal_access', args=[self.tenant.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['created'])
        self.assertTrue(data['username'])
        self.assertTrue(data['password'])

        user = self.tenant.portal_users.first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, RoleEnums.TENANT.value)
        self.assertTrue(user.check_password(data['password']))

    def test_reset_reuses_existing_user(self):
        self.client.force_login(self.staff)
        first = self.client.post(reverse('tenants:portal_access', args=[self.tenant.id])).json()
        second = self.client.post(reverse('tenants:portal_access', args=[self.tenant.id])).json()
        self.assertTrue(first['created'])
        self.assertFalse(second['created'])
        self.assertEqual(first['username'], second['username'])
        self.assertEqual(self.tenant.portal_users.count(), 1)
        # новый пароль действует
        user = self.tenant.portal_users.first()
        self.assertTrue(user.check_password(second['password']))

    def test_portal_role_cannot_issue(self):
        tenant_user = UserAccount.create_tenant_user(self.tenant)
        tenant_user.set_password('pass')
        tenant_user.save()
        self.client.force_login(tenant_user)
        resp = self.client.post(reverse('tenants:portal_access', args=[self.tenant.id]))
        self.assertEqual(resp.status_code, 403)

    def test_get_not_allowed(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse('tenants:portal_access', args=[self.tenant.id]))
        self.assertEqual(resp.status_code, 405)
