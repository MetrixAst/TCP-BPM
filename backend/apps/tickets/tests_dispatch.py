from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount, Employee, Department, Notification
from account.models_rbac import AppPermission, UserPermissionOverride
from hr.models import Company
from tenants.models import Tenant
from tickets.models import ServiceRequest, TicketTypeConfig


class TicketDispatchTest(TestCase):
    """Заявки арендаторов сначала попадают к администраторам ТРЦ (диспетчерам)."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        company = Company.objects.create(name='Disp Co', bin_number='121212121212')
        self.ops = Department.objects.create(name='Эксплуатация', company=company)

        self.dispatcher = UserAccount.objects.create_user(username='trc_admin', password='pass', role='staff')
        Employee.objects.create(user=self.dispatcher, department=self.ops, status='active')
        UserPermissionOverride.objects.create(
            user=self.dispatcher,
            permission=AppPermission.objects.get(code='tickets_dispatch'),
            effect='ALLOW',
        )
        self.plain_staff = UserAccount.objects.create_user(username='plain', password='pass', role='staff')
        Employee.objects.create(user=self.plain_staff, department=self.ops, status='active')
        self.electrician = UserAccount.objects.create_user(username='electrician', password='pass', role='staff')
        Employee.objects.create(user=self.electrician, department=self.ops, status='active')

        self.tenant = Tenant.objects.create(
            name='Бутик', area=10, price=1, phone='', email='t@t.kz', address='', contact='',
        )
        self.tenant_user = UserAccount.objects.create_user(
            username='tenant_user', password='pass', role='tenant', tenant=self.tenant,
        )

    def _create_ticket(self, category='electrical'):
        self.client.force_login(self.tenant_user)
        self.client.post(reverse('tickets:create'), {
            'category': category, 'title': 'Не горит свет', 'description': 'В зале', 'priority': 'medium',
        })
        return ServiceRequest.objects.latest('id')

    def test_new_ticket_notifies_only_dispatchers(self):
        ticket = self._create_ticket()
        notification = Notification.objects.filter(target_type='ticket', target_id=ticket.id).first()
        recipients = set(notification.users.values_list('username', flat=True))
        self.assertIn('trc_admin', recipients)
        self.assertNotIn('plain', recipients)

    def test_dispatcher_sees_and_assigns(self):
        ticket = self._create_ticket()
        self.client.force_login(self.dispatcher)
        self.assertEqual(self.client.get(reverse('tickets:item', args=[ticket.pk])).status_code, 200)

        self.client.post(reverse('tickets:assign', args=[ticket.pk]), {
            'department': self.ops.pk, 'assignee': self.electrician.pk, 'priority': 'high',
        })
        ticket.refresh_from_db()
        self.assertEqual(ticket.assignee, self.electrician)
        self.assertEqual(ticket.department, self.ops)

    def test_plain_staff_cannot_see_tenant_ticket(self):
        ticket = self._create_ticket()
        self.client.force_login(self.plain_staff)
        self.assertEqual(self.client.get(reverse('tickets:item', args=[ticket.pk])).status_code, 404)

    def test_workflow_auto_assign_applied(self):
        TicketTypeConfig.objects.create(ticket_type='electrical', auto_assign_to=self.electrician)
        ticket = self._create_ticket()
        self.assertEqual(ticket.assignee, self.electrician)
        self.assertEqual(ticket.department, self.ops)

    def test_without_config_ticket_stays_unassigned(self):
        ticket = self._create_ticket(category='plumbing')
        self.assertIsNone(ticket.assignee)
