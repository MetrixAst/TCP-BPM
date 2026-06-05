from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount
from account.role_permissions import RoleEnums
from tenants.models import Tenant, TenantCategory, Room

from tickets.models import ServiceRequest
from tickets.enums import TicketStatusEnum, TicketCategoryEnum


class TicketsBaseTest(TestCase):
    def setUp(self):
        # глушим отправку пуш-уведомлений
        patcher = patch('account.tasks.send_notifications_task.delay', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.room = Room.objects.create(number='204', map_id='r204', floor=2)
        self.category = TenantCategory.objects.create(title='Retail')
        self.tenant = Tenant.objects.create(
            name='Coffee Shop', category=self.category, room=self.room,
            area=40, price=900, phone='+77001112233', email='c@test.kz',
            address='Floor 2', contact='Manager',
            start_date='2025-01-01', end_date='2026-01-01',
            discount_date='2025-06-01', increase_type='percent',
        )
        self.tenant_user = UserAccount.create_tenant_user(self.tenant)
        self.tenant_user.set_password('pass')
        self.tenant_user.save()

        self.manager = UserAccount.objects.create_user(
            username='mgr', email='mgr@test.kz', password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.other_tenant_user = UserAccount.create_guest()

    def _new_ticket(self, author=None, status=TicketStatusEnum.NEW.value[0]):
        return ServiceRequest.objects.create(
            tenant=self.tenant,
            author=author or self.tenant_user,
            category=TicketCategoryEnum.PLUMBING.value[0],
            title='Протечка крана',
            description='Капает кран в санузле',
            status=status,
        )


class TicketAccessTest(TicketsBaseTest):
    def test_anonymous_redirected(self):
        resp = self.client.get(reverse('tickets:home'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('next=', resp['Location'])

    def test_tenant_creates_ticket(self):
        self.client.force_login(self.tenant_user)
        resp = self.client.post(reverse('tickets:create'), {
            'category': TicketCategoryEnum.ELECTRICAL.value[0],
            'title': 'Не работает розетка',
            'description': 'Розетка у входа без напряжения',
            'priority': 'medium',
        })
        self.assertEqual(resp.status_code, 302)
        ticket = ServiceRequest.objects.get(title='Не работает розетка')
        self.assertEqual(ticket.author_id, self.tenant_user.id)
        self.assertEqual(ticket.tenant_id, self.tenant.id)
        self.assertEqual(ticket.status, TicketStatusEnum.NEW.value[0])

    def test_tenant_sees_only_own(self):
        own = self._new_ticket()
        foreign = ServiceRequest.objects.create(
            author=self.other_tenant_user,
            category=TicketCategoryEnum.OTHER.value[0],
            title='Чужая', description='x', status=TicketStatusEnum.NEW.value[0],
        )
        self.client.force_login(self.tenant_user)
        self.assertEqual(self.client.get(reverse('tickets:item', args=[own.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse('tickets:item', args=[foreign.id])).status_code, 404)

    def test_manager_sees_all(self):
        own = self._new_ticket()
        foreign = ServiceRequest.objects.create(
            author=self.other_tenant_user,
            category=TicketCategoryEnum.OTHER.value[0],
            title='Чужая', description='x', status=TicketStatusEnum.NEW.value[0],
        )
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse('tickets:item', args=[own.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse('tickets:item', args=[foreign.id])).status_code, 200)


class TicketWorkflowTest(TicketsBaseTest):
    def test_manager_accept_then_complete(self):
        ticket = self._new_ticket()
        self.client.force_login(self.manager)

        # new -> accepted
        resp = self.client.post(reverse('tickets:action', args=[ticket.id]), {'action': 'accept'})
        self.assertEqual(resp.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatusEnum.ACCEPTED.value[0])

        # accepted -> in_progress
        self.client.post(reverse('tickets:action', args=[ticket.id]), {'action': 'start'})
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatusEnum.IN_PROGRESS.value[0])

        # in_progress -> done
        self.client.post(reverse('tickets:action', args=[ticket.id]), {'action': 'complete'})
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatusEnum.DONE.value[0])
        self.assertEqual(ticket.history.count(), 3)

    def test_tenant_cannot_accept(self):
        ticket = self._new_ticket()
        self.client.force_login(self.tenant_user)
        resp = self.client.post(reverse('tickets:action', args=[ticket.id]), {'action': 'accept'})
        self.assertEqual(resp.status_code, 403)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatusEnum.NEW.value[0])

    def test_tenant_can_cancel_own_new(self):
        ticket = self._new_ticket()
        self.client.force_login(self.tenant_user)
        resp = self.client.post(reverse('tickets:action', args=[ticket.id]), {'action': 'cancel'})
        self.assertEqual(resp.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatusEnum.CANCELLED.value[0])

    def test_kanban_status_transition(self):
        ticket = self._new_ticket()
        self.client.force_login(self.manager)
        resp = self.client.post(
            reverse('tickets:kanban_status', args=[ticket.id]),
            data={'status': TicketStatusEnum.ACCEPTED.value[0]},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatusEnum.ACCEPTED.value[0])

    def test_kanban_invalid_transition_rejected(self):
        ticket = self._new_ticket()
        self.client.force_login(self.manager)
        resp = self.client.post(
            reverse('tickets:kanban_status', args=[ticket.id]),
            data={'status': TicketStatusEnum.DONE.value[0]},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatusEnum.NEW.value[0])

    def test_tenant_cannot_use_kanban_status(self):
        ticket = self._new_ticket()
        self.client.force_login(self.tenant_user)
        resp = self.client.post(
            reverse('tickets:kanban_status', args=[ticket.id]),
            data={'status': TicketStatusEnum.ACCEPTED.value[0]},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)


class TicketAssignTest(TicketsBaseTest):
    def test_manager_assigns_department_and_assignee(self):
        from account.models import Department
        from hr.models import Company
        company = Company.objects.create(name='БЦ', bin_number='987654321012')
        dept = Department.objects.create(company=company, name='Эксплуатация', level_type='department')

        ticket = self._new_ticket()
        self.client.force_login(self.manager)
        resp = self.client.post(reverse('tickets:assign', args=[ticket.id]), {
            'department': dept.id,
            'assignee': self.manager.id,
            'priority': 'high',
        })
        self.assertEqual(resp.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.department_id, dept.id)
        self.assertEqual(ticket.assignee_id, self.manager.id)
        self.assertEqual(ticket.priority, 'high')
