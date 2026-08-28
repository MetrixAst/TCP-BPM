from django.test import TestCase
from account.models import UserAccount, Employee, Department
from hr.models import Company
from tickets.models import ServiceRequest
from tickets.services import get_approver, can_bypass_approval


def make_company():
    return Company.objects.create(name='BE16 Co', bin_number='123123123123')


def make_dept(company):
    return Department.objects.create(name='BE16 Dept', company=company)


def make_user(username, role='staff'):
    return UserAccount.objects.create_user(username=username, password='pass', role=role)


def make_employee(user, dept, head=False):
    return Employee.objects.create(user=user, department=dept, head=head, status='active')


class GetApproverTest(TestCase):

    def setUp(self):
        self.company = make_company()
        self.dept = make_dept(self.company)
        self.staff_user = make_user('staff_be16')
        self.head_user = make_user('head_be16')
        self.admin_user = make_user('admin_be16', role='administrator')
        self.staff_emp = make_employee(self.staff_user, self.dept, head=False)
        self.head_emp = make_employee(self.head_user, self.dept, head=True)

    def test_returns_head_of_department(self):
        approver = get_approver(self.staff_user)
        self.assertEqual(approver, self.head_user)

    def test_excludes_self_as_approver(self):
        """Руководитель не согласует сам себя."""
        approver = get_approver(self.head_user)
        self.assertNotEqual(approver, self.head_user)

    def test_fallback_to_admin_when_no_head(self):
        dept2 = Department.objects.create(name='No Head Dept', company=self.company)
        user2 = make_user('staff_no_head')
        make_employee(user2, dept2, head=False)
        approver = get_approver(user2)
        self.assertEqual(approver, self.admin_user)


class CanBypassApprovalTest(TestCase):

    def setUp(self):
        self.company = make_company()
        self.dept = make_dept(self.company)
        self.admin = make_user('admin_bypass', role='administrator')
        self.staff = make_user('staff_bypass')
        self.head_user = make_user('head_bypass')
        make_employee(self.staff, self.dept, head=False)
        make_employee(self.head_user, self.dept, head=True)

    def test_admin_can_bypass(self):
        self.assertTrue(can_bypass_approval(self.admin))

    def test_head_can_bypass(self):
        self.assertTrue(can_bypass_approval(self.head_user))

    def test_staff_cannot_bypass(self):
        self.assertFalse(can_bypass_approval(self.staff))