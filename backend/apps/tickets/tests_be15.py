from django.test import TestCase
from django.utils import timezone

from account.models import UserAccount
from tickets.models import ServiceRequest, TicketTypeConfig, ApprovalDecision
from tickets.enums import TicketStatusEnum


def make_user(username, role='staff'):
    return UserAccount.objects.create_user(username=username, password='pass', role=role)


def make_ticket(author, status='new'):
    return ServiceRequest.objects.create(
        author=author,
        title='Test Ticket',
        category='other',
        priority='medium',
        status=status,
    )


class TicketStatusEnumTest(TestCase):

    def test_new_statuses_exist(self):
        self.assertEqual(TicketStatusEnum.PENDING_APPROVAL.value[0], 'pending_approval')
        self.assertEqual(TicketStatusEnum.APPROVED.value[0], 'approved')

    def test_old_statuses_preserved(self):
        self.assertEqual(TicketStatusEnum.NEW.value[0], 'new')
        self.assertEqual(TicketStatusEnum.ACCEPTED.value[0], 'accepted')
        self.assertEqual(TicketStatusEnum.IN_PROGRESS.value[0], 'in_progress')
        self.assertEqual(TicketStatusEnum.DONE.value[0], 'done')
        self.assertEqual(TicketStatusEnum.REJECTED.value[0], 'rejected')
        self.assertEqual(TicketStatusEnum.CANCELLED.value[0], 'cancelled')


class TicketTransitionsTest(TestCase):

    def test_in_progress_can_request_approval(self):
        from tickets.enums import TICKET_TRANSITIONS
        transitions = TICKET_TRANSITIONS.get('in_progress', {})
        self.assertIn('request_approval', transitions)
        self.assertEqual(transitions['request_approval']['next'], 'pending_approval')

    def test_pending_approval_can_approve(self):
        from tickets.enums import TICKET_TRANSITIONS
        transitions = TICKET_TRANSITIONS.get('pending_approval', {})
        self.assertIn('approve', transitions)
        self.assertEqual(transitions['approve']['next'], 'approved')

    def test_pending_approval_can_reject(self):
        from tickets.enums import TICKET_TRANSITIONS
        transitions = TICKET_TRANSITIONS.get('pending_approval', {})
        self.assertIn('reject', transitions)
        self.assertEqual(transitions['reject']['next'], 'rejected')


class TicketTypeConfigTest(TestCase):

    def test_create_config(self):
        config = TicketTypeConfig.objects.create(
            ticket_type='electrical',  
            requires_approval=True,
        )
        self.assertTrue(config.requires_approval)

    def test_default_no_approval(self):
        config = TicketTypeConfig.objects.create(ticket_type='cleaning')  
        self.assertFalse(config.requires_approval)


class ApprovalDecisionTest(TestCase):

    def setUp(self):
        self.admin = make_user('admin_be15', role='administrator')
        self.author = make_user('author_be15')
        self.ticket = make_ticket(self.author, status='pending_approval')

    def test_create_approval_decision(self):
        decision = ApprovalDecision.objects.create(
            ticket=self.ticket,
            actor=self.admin,
            decision='approve',
            comment='Всё хорошо',
            ip_address='127.0.0.1',
        )
        self.assertEqual(decision.decision, 'approve')
        self.assertEqual(decision.actor, self.admin)
        self.assertEqual(decision.ticket, self.ticket)

    def test_create_reject_decision(self):
        decision = ApprovalDecision.objects.create(
            ticket=self.ticket,
            actor=self.admin,
            decision='reject',
            comment='Не соответствует требованиям',
            ip_address='127.0.0.1',
        )
        self.assertEqual(decision.decision, 'reject')

    def test_active_tickets_not_affected(self):
        """Активные заявки в статусе new не переводятся повторно."""
        active_ticket = make_ticket(self.author, status='new')
        self.assertEqual(active_ticket.status, 'new')
        active_ticket.refresh_from_db()
        self.assertEqual(active_ticket.status, 'new')