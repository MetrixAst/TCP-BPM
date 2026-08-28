from django.test import TestCase, RequestFactory
from account.models import UserAccount, Employee, Department
from hr.models import Company
from tickets.models import ServiceRequest, ApprovalDecision
from tickets.enums import TicketStatusEnum


def make_company():
    return Company.objects.create(name='BE18 Co', bin_number='111999888777')


def make_dept(company):
    return Department.objects.create(name='BE18 Dept', company=company)


def make_user(username, role='staff'):
    return UserAccount.objects.create_user(username=username, password='pass', role=role)


def make_employee(user, dept, head=False):
    return Employee.objects.create(user=user, department=dept, head=head, status='active')


def make_ticket(author, status='pending_approval'):
    return ServiceRequest.objects.create(
        author=author,
        title='Test BE18',
        category='other',
        priority='medium',
        status=status,
    )


class ApprovalHistoryTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.company = make_company()
        self.dept = make_dept(self.company)
        self.admin = make_user('admin_be18', role='administrator')
        self.staff = make_user('staff_be18')
        make_employee(self.staff, self.dept)
        self.ticket = make_ticket(self.staff)

    def test_approval_decision_stores_all_fields(self):
        decision = ApprovalDecision.objects.create(
            ticket=self.ticket,
            actor=self.admin,
            decision='approve',
            comment='Всё хорошо',
            ip_address='127.0.0.1',
        )
        self.assertEqual(decision.decision, 'approve')
        self.assertEqual(decision.actor, self.admin)
        self.assertEqual(decision.comment, 'Всё хорошо')
        self.assertEqual(decision.ip_address, '127.0.0.1')
        self.assertIsNotNone(decision.created_at)

    def test_approval_history_endpoint(self):
        ApprovalDecision.objects.create(
            ticket=self.ticket,
            actor=self.admin,
            decision='reject',
            comment='причина отклонения заявки',
            ip_address='127.0.0.1',
        )
        from django.test import Client
        client = Client()
        client.login(username='admin_be18', password='pass')
        r = client.get(f'/tickets/item/{self.ticket.pk}/approval-history/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data['ok'])
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['decision'], 'reject')
        self.assertEqual(data['results'][0]['comment'], 'причина отклонения заявки')
        self.assertIsNotNone(data['results'][0]['created_at'])
        self.assertIsNotNone(data['results'][0]['actor'])


class NotificationsOnApprovalTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.company = make_company()
        self.dept = make_dept(self.company)
        self.admin = make_user('admin_be18_notif', role='administrator')
        self.staff = make_user('staff_be18_notif')
        make_employee(self.staff, self.dept)
        self.ticket = make_ticket(self.admin, status='pending_approval')

    def test_approve_creates_notification(self):
        from account.models import Notification
        count_before = Notification.objects.count()
        request = self.factory.post('/')
        request.user = self.admin
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        self.ticket.apply_action(request, 'approve', comment='')
        count_after = Notification.objects.count()
        self.assertGreater(count_after, count_before)

    def test_reject_creates_notification(self):
        from account.models import Notification
        count_before = Notification.objects.count()
        request = self.factory.post('/')
        request.user = self.admin
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        self.ticket.apply_action(request, 'reject', comment='причина отклонения')
        count_after = Notification.objects.count()
        self.assertGreater(count_after, count_before)