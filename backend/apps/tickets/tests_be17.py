from django.test import TestCase, RequestFactory
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company
from tickets.models import ServiceRequest, ApprovalDecision
from tickets.enums import TicketStatusEnum


def make_company():
    return Company.objects.create(name='BE17 Co', bin_number='777888999000')


def make_dept(company):
    return Department.objects.create(name='BE17 Dept', company=company)


def make_user(username, role='staff'):
    return UserAccount.objects.create_user(username=username, password='pass', role=role)


def make_employee(user, dept, head=False):
    return Employee.objects.create(user=user, department=dept, head=head, status='active')


def make_ticket(author, status='new'):
    return ServiceRequest.objects.create(
        author=author,
        title='Test BE17',
        category='other',
        priority='medium',
        status=status,
    )


class RejectCommentRequiredTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.company = make_company()
        self.dept = make_dept(self.company)
        self.admin = make_user('admin_be17', role='administrator')
        self.ticket = make_ticket(self.admin, status='pending_approval')

    def test_reject_without_comment_fails(self):
        request = self.factory.post('/')
        request.user = self.admin
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        ok, error = self.ticket.apply_action(request, 'reject', comment='ок')
        self.assertFalse(ok)
        self.assertIn('обязателен', error)

    def test_reject_with_comment_succeeds(self):
        request = self.factory.post('/')
        request.user = self.admin
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        ok, error = self.ticket.apply_action(request, 'reject', comment='причина отклонения заявки')
        self.assertTrue(ok)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatusEnum.REJECTED.value[0])

    def test_reject_creates_approval_decision(self):
        request = self.factory.post('/')
        request.user = self.admin
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        self.ticket.apply_action(request, 'reject', comment='причина отклонения заявки')
        decision = ApprovalDecision.objects.filter(ticket=self.ticket).first()
        self.assertIsNotNone(decision)
        self.assertEqual(decision.decision, 'reject')
        self.assertEqual(decision.actor, self.admin)


class PendingApprovalVisibilityTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.company = make_company()
        self.dept = make_dept(self.company)
        self.admin = make_user('admin_vis', role='administrator')
        self.staff = make_user('staff_vis', role='staff')
        self.head_user = make_user('head_vis', role='staff')
        make_employee(self.staff, self.dept, head=False)
        make_employee(self.head_user, self.dept, head=True)
        self.ticket = make_ticket(self.staff, status='pending_approval')

    def test_admin_sees_pending_approval(self):
        request = self.factory.get('/')
        request.user = self.admin
        qs = ServiceRequest.get_available_queryset(request)
        self.assertIn(self.ticket, qs)

    def test_head_sees_pending_approval(self):
        request = self.factory.get('/')
        request.user = self.head_user
        qs = ServiceRequest.get_available_queryset(request)
        self.assertIn(self.ticket, qs)

    def test_staff_cannot_see_pending_approval(self):
        other_staff = make_user('other_staff_vis', role='staff')
        make_employee(other_staff, self.dept, head=False)
        request = self.factory.get('/')
        request.user = other_staff
        qs = ServiceRequest.get_available_queryset(request)
        self.assertNotIn(self.ticket, qs)


class SLAEscalationTest(TestCase):

    def setUp(self):
        self.company = make_company()
        self.dept = make_dept(self.company)
        self.admin = make_user('admin_sla', role='administrator')
        self.staff = make_user('staff_sla', role='staff')
        make_employee(self.staff, self.dept)

    def test_escalation_task_runs(self):
        ticket = make_ticket(self.staff, status='pending_approval')
        ServiceRequest.objects.filter(pk=ticket.pk).update(
            updated_at=timezone.now() - timedelta(hours=50)
        )
        from tickets.tasks import sla_escalation
        result = sla_escalation()
        self.assertIn('1', result)