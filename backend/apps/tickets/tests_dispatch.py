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


class TicketApprovePermissionTest(TestCase):
    """Право «согласование любых заявок» — без роли администратора и без руководства отделом."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        company = Company.objects.create(name='Appr Co', bin_number='909090909090')
        dept = Department.objects.create(name='Склад', company=company)
        self.author = UserAccount.objects.create_user(username='appr_author', password='pass', role='staff')
        Employee.objects.create(user=self.author, department=dept, status='active')
        self.deputy = UserAccount.objects.create_user(username='deputy', password='pass', role='staff')
        Employee.objects.create(user=self.deputy, department=dept, status='active')
        self.ticket = ServiceRequest.objects.create(
            author=self.author, title='Закупка', description='-', status='pending_approval',
        )

    def test_deputy_with_permission_approves(self):
        self.client.force_login(self.deputy)
        self.assertEqual(self.client.get(reverse('tickets:approvals')).status_code, 403)

        UserPermissionOverride.objects.create(
            user=self.deputy, permission=AppPermission.objects.get(code='tickets_approve'), effect='ALLOW',
        )
        cache.clear()
        queue = self.client.get(reverse('tickets:approvals'))
        self.assertEqual(queue.status_code, 200)

        self.client.post(reverse('tickets:action', args=[self.ticket.pk]), {'action': 'approve'})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'approved')


class TicketVisibilityTest(TestCase):
    """Общий поток заявок видят только администраторы и диспетчеры."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        company = Company.objects.create(name='Vis Co', bin_number='131313131313')
        self.ops = Department.objects.create(name='Эксплуатация', company=company)
        self.it = Department.objects.create(name='ИТ', company=company)

        self.ops_head = UserAccount.objects.create_user(username='ops_head', password='pass', role='staff')
        Employee.objects.create(user=self.ops_head, department=self.ops, status='active', head=True)
        self.it_head = UserAccount.objects.create_user(username='it_head', password='pass', role='staff')
        Employee.objects.create(user=self.it_head, department=self.it, status='active', head=True)
        self.worker = UserAccount.objects.create_user(username='worker', password='pass', role='staff')
        Employee.objects.create(user=self.worker, department=self.ops, status='active')
        self.admin = UserAccount.objects.create_user(username='trc_boss', password='pass', role='administrator')

        tenant = Tenant.objects.create(name='Кафе', area=10, price=1, phone='', email='c@c.kz', address='', contact='')
        self.unrouted = ServiceRequest.objects.create(tenant=tenant, title='Новая', description='x')
        self.ops_ticket = ServiceRequest.objects.create(
            tenant=tenant, title='Свет', description='x', department=self.ops, assignee=self.worker,
        )

    def _visible(self, user):
        self.client.force_login(user)
        response = self.client.get(reverse('tickets:home'))
        self.assertEqual(response.status_code, 200)
        return {item.pk for item in response.context['paginator'].items}

    def test_admin_sees_everything(self):
        self.assertEqual(self._visible(self.admin), {self.unrouted.pk, self.ops_ticket.pk})

    def test_department_head_sees_only_own_department(self):
        self.assertEqual(self._visible(self.ops_head), {self.ops_ticket.pk})
        self.assertEqual(self._visible(self.it_head), set())

    def test_assignee_sees_assigned_ticket(self):
        self.assertEqual(self._visible(self.worker), {self.ops_ticket.pk})
        self.client.force_login(self.worker)
        self.assertEqual(self.client.get(reverse('tickets:item', args=[self.unrouted.pk])).status_code, 404)
