from datetime import date
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from account.models import UserAccount, Employee, Department
from account.role_permissions import RoleEnums
from hr.models import Company, LeaveRequest, LeaveType
from hr.enums import LeaveStatusEnum
from finances.models import GeneratedInvoice, BudgetCategory, BudgetItem
from finances.tests import make_tenant
from audit.models import AuditLog
from audit.context import set_request_context, clear_request_context


class AuditSignalTestCase(TestCase):
    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            username='audit_admin',
            password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        set_request_context(user=self.admin, ip_address='127.0.0.1', user_agent='test')

    def tearDown(self):
        clear_request_context()

    def test_employee_create_logs_audit(self):
        company = Company.objects.create(name='AuditCo', bin_number='111111111111')
        dept = Department.objects.create(name='HR', company=company)
        user = UserAccount.objects.create_user(
            username='emp_audit',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        before = AuditLog.objects.count()
        Employee.objects.create(user=user, department=dept, iin='990101300456')
        self.assertEqual(AuditLog.objects.count(), before + 1)
        log = AuditLog.objects.latest('created_at')
        self.assertEqual(log.action, AuditLog.Action.CREATE)
        self.assertEqual(log.object_type, 'Employee')
        self.assertEqual(log.user, self.admin)

    def test_generated_invoice_update_logs_changes(self):
        tenant = make_tenant()
        inv = GeneratedInvoice.objects.create(
            tenant=tenant,
            number='AUD-001',
            total_amount=Decimal('1000'),
            status=GeneratedInvoice.Status.CREATED,
        )
        inv.status = GeneratedInvoice.Status.SENT
        inv.save()
        update_log = AuditLog.objects.filter(
            object_type='GeneratedInvoice',
            object_id=str(inv.pk),
            action=AuditLog.Action.UPDATE,
        ).latest('created_at')
        self.assertIn('status', update_log.changes)

    def test_leave_status_change_logs_update(self):
        company = Company.objects.create(name='LeaveCo', bin_number='222222222222')
        dept = Department.objects.create(name='Ops', company=company)
        emp_user = UserAccount.objects.create_user(
            username='leave_emp',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        employee = Employee.objects.create(user=emp_user, department=dept, iin='990101300789')
        leave_type = LeaveType.objects.create(name='Основной')
        leave = LeaveRequest.objects.create(
            employee=employee,
            leave_type=leave_type,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 5),
            status=LeaveStatusEnum.PENDING,
        )
        leave.status = LeaveStatusEnum.APPROVED
        leave.save()
        log = AuditLog.objects.filter(
            object_type='LeaveRequest',
            action=AuditLog.Action.UPDATE,
        ).latest('created_at')
        self.assertIn('status', log.changes)

    def test_budget_item_delete_logs_audit(self):
        cat = BudgetCategory.objects.create(
            name='TestCat',
            category_type=BudgetCategory.Type.EXPENSE,
        )
        item = BudgetItem.objects.create(category=cat, year=2026, month=1, plan=Decimal('500'))
        item_id = str(item.pk)
        item.delete()
        self.assertTrue(
            AuditLog.objects.filter(
                object_type='BudgetItem',
                object_id=item_id,
                action=AuditLog.Action.DELETE,
            ).exists()
        )


class AuditLogViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = UserAccount.objects.create_user(
            username='view_admin',
            password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.staff = UserAccount.objects.create_user(
            username='view_staff',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        AuditLog.objects.create(
            user=self.admin,
            action=AuditLog.Action.LOGIN,
            object_type='UserAccount',
            object_id=str(self.admin.pk),
            object_repr='login',
        )
        self.url = reverse('audit:log')

    def test_staff_forbidden_403(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_admin_list_200(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Журнал аудита')

    def test_admin_filter_by_action(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {'action': AuditLog.Action.LOGIN})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'login')
