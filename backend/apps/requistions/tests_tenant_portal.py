from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount
from account.role_permissions import RoleEnums
from tenants.models import Tenant, TenantCategory, Room
from purchases.models import Supplier
from requistions.models import Requistion
from requistions.enums import RequstionTypesEnum


class TenantPortalTest(TestCase):
    def setUp(self):
        self.room = Room.objects.create(number='101', map_id='r101', floor=1)
        self.category = TenantCategory.objects.create(title='Retail')
        self.tenant = Tenant.objects.create(
            name='Test Shop',
            category=self.category,
            room=self.room,
            area=50,
            price=1000,
            phone='+77001112233',
            email='shop@test.kz',
            address='Floor 1',
            contact='Manager',
            start_date='2025-01-01',
            end_date='2026-01-01',
            discount_date='2025-06-01',
            increase_type='percent',
        )
        self.tenant_user = UserAccount.create_tenant_user(self.tenant)
        self.tenant_user.set_password('testpass')
        self.tenant_user.save()

    def test_tenant_role_and_fk(self):
        self.assertEqual(self.tenant_user.role, RoleEnums.TENANT.value)
        self.assertEqual(self.tenant_user.tenant_id, self.tenant.pk)

    @patch('account.tasks.send_notifications_task.delay')
    def test_tenant_can_create_requisition(self, _mock_delay):
        req = Requistion.objects.create(
            requistion_type=RequstionTypesEnum.WORKS.value[0],
            user=self.tenant_user,
            status='',
            supplier=Supplier.objects.create(
                name='S', status='checked', address2='A',
            ),
        )

        class FakeRequest:
            user = self.tenant_user

        req.set_action(FakeRequest(), 'create')
        req.refresh_from_db()
        self.assertEqual(req.status, 'draft')
        self.assertEqual(req.user_id, self.tenant_user.pk)

    def test_tenant_sees_only_own_requisitions(self):
        supplier = Supplier.objects.create(
            name='Supplier Test',
            status='checked',
            address2='Addr',
        )
        other = UserAccount.create_guest()
        Requistion.objects.create(
            requistion_type=RequstionTypesEnum.WORKS.value[0],
            user=other,
            status='draft',
            supplier=supplier,
        )
        own = Requistion.objects.create(
            requistion_type=RequstionTypesEnum.WORKS.value[0],
            user=self.tenant_user,
            status='draft',
            supplier=supplier,
        )

        class FakeRequest:
            user = self.tenant_user

        qs = Requistion.get_available_queryset(FakeRequest())
        self.assertIn(own, qs)
        self.assertEqual(qs.count(), 1)


class RequistionAccessControlTest(TestCase):
    """Регрессия prod-готовности: доступ и безопасные действия по заявкам."""

    def setUp(self):
        self.supplier = Supplier.objects.create(
            name='S', status='checked', address2='A',
        )
        self.author = UserAccount.create_guest()
        self.observer = UserAccount.create_guest()

    def _make_requisition(self, status='draft'):
        req = Requistion.objects.create(
            requistion_type=RequstionTypesEnum.WORKS.value[0],
            user=self.author,
            status=status,
            supplier=self.supplier,
        )
        req.observers.add(self.observer)
        return req

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse('requistions:home'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('next=', resp['Location'])

    def test_action_get_not_allowed(self):
        req = self._make_requisition()
        self.client.force_login(self.author)
        resp = self.client.get(reverse('requistions:action', args=[req.id]))
        self.assertEqual(resp.status_code, 403)

    def test_observer_cannot_delete(self):
        req = self._make_requisition()
        self.client.force_login(self.observer)
        resp = self.client.post(
            reverse('requistions:action', args=[req.id]),
            {'action': 'cancel'},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Requistion.objects.filter(pk=req.id).exists())

    def test_observer_cannot_open_edit(self):
        req = self._make_requisition()
        self.client.force_login(self.observer)
        resp = self.client.get(reverse('requistions:edit', args=[req.id]))
        self.assertIn(resp.status_code, (403, 404))
