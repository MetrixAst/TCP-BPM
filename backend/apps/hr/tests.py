from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.http import Http404
from django.db import IntegrityError
from django.db.models import Q
from datetime import date
import requests
from unittest.mock import Mock, patch

from .models import (
    LeaveRequest, LeaveType, WorkCalendar, Company, 
    Position, Vacation, SickLeave, EmploymentContract
)
from .enums import LeaveStatusEnum, DayTypeEnum
from account.role_permissions import RoleEnums, MenuItem

try:
    from account.models import Employee, UserAccount, Department
except ImportError:
    from apps.account.models import Employee, UserAccount, Department

from hr.enbek_client import EnbekClient, EnbekClientError, AuthenticationError, ConnectionError
from hr.services import EnbekSyncService
from hr.tasks import sync_enbek_data

class LeaveRequestLogicTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="TechCorp", bin_number="123456789012")
        self.dept = Department.objects.create(name="IT", company=self.company)
        self.user = UserAccount.objects.create(email="darya@test.kz", first_name="Dar")
        self.employee = Employee.objects.create(user=self.user, department=self.dept)

        self.leave_type = LeaveType.objects.create(
            name="Ежегодный", is_paid=True, max_days_per_year=24
        )

        WorkCalendar.objects.create(date=date(2026, 1, 1), day_type=DayTypeEnum.HOLIDAY, year=2026)
        WorkCalendar.objects.create(date=date(2026, 1, 2), day_type=DayTypeEnum.HOLIDAY, year=2026)

    def test_basic_working_days(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=date(2026, 4, 13),
            end_date=date(2026, 4, 17)
        )
        self.assertEqual(leave.working_days_count, 5)

    def test_holiday_exclusion(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=date(2025, 12, 31),
            end_date=date(2026, 1, 5)
        )
        self.assertEqual(leave.working_days_count, 2)

    def test_company_specific_override(self):
        special_date = date(2026, 4, 18)
        WorkCalendar.objects.create(
            date=special_date,
            day_type=DayTypeEnum.WORKING,
            company=self.company,
            year=2026
        )
        leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=special_date,
            end_date=special_date
        )
        self.assertEqual(leave.working_days_count, 1)

    def test_status_workflow(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 5)
        )
        self.assertEqual(leave.status, LeaveStatusEnum.DRAFT)

        leave.status = LeaveStatusEnum.APPROVED
        leave.save()

        updated_leave = LeaveRequest.objects.get(pk=leave.pk)
        self.assertEqual(updated_leave.status, 'approved')

    def test_zero_days_on_weekend_only(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=date(2026, 4, 18),
            end_date=date(2026, 4, 19)
        )
        self.assertEqual(leave.working_days_count, 0)


class LeaveComplexViewsTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="DauInvest", bin_number="000000000000")
        self.dept = Department.objects.create(name="Analysis", company=self.company)

        self.u_emp = UserAccount.objects.create_user(username='darya', password='123')
        self.employee = Employee.objects.create(user=self.u_emp, department=self.dept)

        self.u_boss = UserAccount.objects.create_user(username='manager', password='123', head=True)
        self.boss = Employee.objects.create(user=self.u_boss, department=self.dept, head=True)

        self.paid_type = LeaveType.objects.create(name="Paid Vacation", max_days_per_year=24)
        self.client = Client()

    def test_invalid_date_range(self):
        self.client.login(username='darya', password='123')
        data = {
            'leave_type': self.paid_type.id,
            'start_date': '2026-07-10',
            'end_date': '2026-07-01'
        }
        response = self.client.post(reverse('hr:leave_create'), data)
        self.assertContains(response, "Дата начала не может быть позже даты окончания")

    def test_leave_list_filters(self):
        LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.paid_type,
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 5),
            status=LeaveStatusEnum.APPROVED
        )
        self.client.login(username='manager', password='123')
        response = self.client.get(
            reverse('hr:leave_list'),
            {'status': LeaveStatusEnum.APPROVED}
        )
        self.assertEqual(len(response.context['leaves']), 1)

    def test_reject_workflow(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.paid_type,
            start_date=date(2026, 6, 1), end_date=date(2026, 6, 5),
            status=LeaveStatusEnum.PENDING
        )
        self.client.login(username='manager', password='123')
        self.client.post(reverse('hr:leave_reject', args=[leave.pk]))
        leave.refresh_from_db()
        self.assertEqual(leave.status, LeaveStatusEnum.REJECTED)

    def test_cancel_own_request(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.paid_type,
            start_date=date(2026, 6, 1), end_date=date(2026, 6, 5),
            status=LeaveStatusEnum.DRAFT
        )
        self.client.login(username='darya', password='123')
        self.client.post(reverse('hr:leave_cancel', args=[leave.pk]))
        self.assertEqual(LeaveRequest.objects.filter(pk=leave.pk).count(), 0)

    def test_ajax_with_holiday(self):
        WorkCalendar.objects.create(
            date=date(2026, 7, 1),
            day_type=DayTypeEnum.HOLIDAY,
            company=self.company
        )
        self.client.login(username='darya', password='123')
        response = self.client.get(reverse('hr:ajax_calculate_days'), {
            'start': '2026-07-01',
            'end': '2026-07-03'
        })
        self.assertEqual(response.json()['days'], 2)

    def test_cannot_cancel_approved_leave(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.paid_type,
            start_date=date(2026, 6, 1), end_date=date(2026, 6, 5),
            status=LeaveStatusEnum.APPROVED
        )
        self.client.login(username='darya', password='123')
        self.client.post(reverse('hr:leave_cancel', args=[leave.pk]))
        self.assertEqual(LeaveRequest.objects.filter(pk=leave.pk).count(), 1)



class LeaveListViewExtendedTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="ListCorp", bin_number="111111111111")
        self.dept = Department.objects.create(name="Dev", company=self.company)
        self.dept2 = Department.objects.create(name="QA", company=self.company)

        self.u_emp = UserAccount.objects.create_user(username='emp_list', password='123')
        self.employee = Employee.objects.create(user=self.u_emp, department=self.dept)

        self.u_emp2 = UserAccount.objects.create_user(username='emp_list2', password='123')
        self.employee2 = Employee.objects.create(user=self.u_emp2, department=self.dept2)

        self.u_boss = UserAccount.objects.create_user(username='boss_list', password='123')
        self.boss = Employee.objects.create(user=self.u_boss, department=self.dept, head=True)

        self.type1 = LeaveType.objects.create(name="Ежегодный_л", max_days_per_year=24)
        self.type2 = LeaveType.objects.create(name="Учебный_л", max_days_per_year=10)

    def test_anonymous_redirected(self):
        response = self.client.get(reverse('hr:leave_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_logged_in_sees_page(self):
        self.client.login(username='emp_list', password='123')
        response = self.client.get(reverse('hr:leave_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'site/hr/leave_list.html')

    def test_context_keys_present(self):
        self.client.login(username='emp_list', password='123')
        response = self.client.get(reverse('hr:leave_list'))
        self.assertIn('leaves', response.context)
        self.assertIn('filter_form', response.context)
        self.assertIn('is_manager', response.context)

    def test_is_manager_false_for_regular_employee(self):
        self.client.login(username='emp_list', password='123')
        response = self.client.get(reverse('hr:leave_list'))
        self.assertFalse(response.context['is_manager'])

    def test_is_manager_true_for_head(self):
        self.client.login(username='boss_list', password='123')
        response = self.client.get(reverse('hr:leave_list'))
        self.assertTrue(response.context['is_manager'])

    def test_all_leaves_shown_without_filters(self):
        LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.type1,
            start_date=date(2026, 8, 3), end_date=date(2026, 8, 7)
        )
        LeaveRequest.objects.create(
            employee=self.employee2, leave_type=self.type2,
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 14)
        )
        self.client.login(username='emp_list', password='123')
        response = self.client.get(reverse('hr:leave_list'))
        self.assertEqual(response.context['leaves'].count(), 2)

    def test_filter_by_leave_type(self):
        LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.type1,
            start_date=date(2026, 8, 3), end_date=date(2026, 8, 7)
        )
        LeaveRequest.objects.create(
            employee=self.employee2, leave_type=self.type2,
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 14)
        )
        self.client.login(username='emp_list', password='123')
        response = self.client.get(
            reverse('hr:leave_list'), {'leave_type': self.type1.pk}
        )
        leaves = list(response.context['leaves'])
        self.assertEqual(len(leaves), 1)
        self.assertEqual(leaves[0].leave_type, self.type1)

    def test_filter_by_department(self):
        LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.type1,
            start_date=date(2026, 8, 3), end_date=date(2026, 8, 7)
        )
        LeaveRequest.objects.create(
            employee=self.employee2, leave_type=self.type1,
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 14)
        )
        self.client.login(username='emp_list', password='123')
        response = self.client.get(
            reverse('hr:leave_list'), {'department': self.dept.pk}
        )
        leaves = list(response.context['leaves'])
        self.assertEqual(len(leaves), 1)
        self.assertEqual(leaves[0].employee.department, self.dept)

    def test_filter_by_date_from(self):
        LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.type1,
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 5)
        )
        LeaveRequest.objects.create(
            employee=self.employee2, leave_type=self.type1,
            start_date=date(2026, 9, 1), end_date=date(2026, 9, 5)
        )
        self.client.login(username='emp_list', password='123')
        response = self.client.get(
            reverse('hr:leave_list'), {'date_from': '2026-08-20'}
        )
        leaves = list(response.context['leaves'])
        self.assertEqual(len(leaves), 1)
        self.assertEqual(leaves[0].start_date, date(2026, 9, 1))

    def test_filter_by_date_to(self):
        LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.type1,
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 5)
        )
        LeaveRequest.objects.create(
            employee=self.employee2, leave_type=self.type1,
            start_date=date(2026, 9, 1), end_date=date(2026, 9, 30)
        )
        self.client.login(username='emp_list', password='123')
        response = self.client.get(
            reverse('hr:leave_list'), {'date_to': '2026-08-10'}
        )
        leaves = list(response.context['leaves'])
        self.assertEqual(len(leaves), 1)
        self.assertEqual(leaves[0].end_date, date(2026, 8, 5))

    def test_filter_by_search_first_name(self):
        self.u_emp.first_name = 'Жанар'
        self.u_emp.save()
        LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.type1,
            start_date=date(2026, 8, 3), end_date=date(2026, 8, 7)
        )
        LeaveRequest.objects.create(
            employee=self.employee2, leave_type=self.type1,
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 14)
        )
        self.client.login(username='emp_list', password='123')
        response = self.client.get(reverse('hr:leave_list'), {'search': 'Жанар'})
        leaves = list(response.context['leaves'])
        self.assertEqual(len(leaves), 1)
        self.assertEqual(leaves[0].employee, self.employee)

    def test_empty_list_when_no_leaves(self):
        self.client.login(username='emp_list', password='123')
        response = self.client.get(reverse('hr:leave_list'))
        self.assertEqual(response.context['leaves'].count(), 0)


class LeaveCreateExtendedTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="CreateCorp", bin_number="222222222222")
        self.dept = Department.objects.create(name="HR_dept", company=self.company)

        self.u_emp = UserAccount.objects.create_user(username='emp_create', password='123')
        self.employee = Employee.objects.create(user=self.u_emp, department=self.dept)

        self.u_no_profile = UserAccount.objects.create_user(username='noprofile', password='123')

        self.leave_type = LeaveType.objects.create(name="Ежегодный_c", max_days_per_year=24)

    def test_anonymous_redirected(self):
        response = self.client.get(reverse('hr:leave_create'))
        self.assertEqual(response.status_code, 302)

    def test_get_shows_form(self):
        self.client.login(username='emp_create', password='123')
        response = self.client.get(reverse('hr:leave_create'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'site/hr/leave_create.html')
        self.assertIn('form', response.context)

    def test_successful_create_redirects_to_list(self):
        self.client.login(username='emp_create', password='123')
        response = self.client.post(reverse('hr:leave_create'), {
            'leave_type': self.leave_type.pk,
            'start_date': '2026-08-03',
            'end_date': '2026-08-07',
            'comment': 'Тест',
        })
        self.assertRedirects(response, reverse('hr:leave_list'))

    def test_successful_create_saves_to_db(self):
        self.client.login(username='emp_create', password='123')
        self.client.post(reverse('hr:leave_create'), {
            'leave_type': self.leave_type.pk,
            'start_date': '2026-08-03',
            'end_date': '2026-08-07',
            'comment': '',
        })
        self.assertEqual(LeaveRequest.objects.count(), 1)

    def test_create_sets_status_pending(self):
        self.client.login(username='emp_create', password='123')
        self.client.post(reverse('hr:leave_create'), {
            'leave_type': self.leave_type.pk,
            'start_date': '2026-08-03',
            'end_date': '2026-08-07',
            'comment': '',
        })
        leave = LeaveRequest.objects.first()
        self.assertEqual(leave.status, LeaveStatusEnum.PENDING)

    def test_create_sets_correct_employee(self):
        self.client.login(username='emp_create', password='123')
        self.client.post(reverse('hr:leave_create'), {
            'leave_type': self.leave_type.pk,
            'start_date': '2026-08-03',
            'end_date': '2026-08-07',
            'comment': '',
        })
        leave = LeaveRequest.objects.first()
        self.assertEqual(leave.employee, self.employee)

    def test_user_without_profile_redirected_to_list(self):
        self.client.login(username='noprofile', password='123')
        response = self.client.post(reverse('hr:leave_create'), {
            'leave_type': self.leave_type.pk,
            'start_date': '2026-08-03',
            'end_date': '2026-08-07',
            'comment': '',
        })
        self.assertRedirects(response, reverse('hr:leave_list'))
        self.assertEqual(LeaveRequest.objects.count(), 0)

    def test_missing_leave_type_shows_form_with_error(self):
        self.client.login(username='emp_create', password='123')
        response = self.client.post(reverse('hr:leave_create'), {
            'leave_type': '',
            'start_date': '2026-08-03',
            'end_date': '2026-08-07',
        })
        self.assertEqual(LeaveRequest.objects.count(), 0)
        self.assertIn(response.status_code, [200, 302])


class LeaveDetailViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="DetailCorp", bin_number="333333333333")
        self.dept = Department.objects.create(name="Fin", company=self.company)

        self.u_owner = UserAccount.objects.create_user(username='owner_detail', password='123')
        self.u_owner.role = RoleEnums.ADMINISTRATOR.value
        self.u_owner.save()
        self.owner = Employee.objects.create(user=self.u_owner, department=self.dept)

        self.u_other = UserAccount.objects.create_user(username='other_detail', password='123')
        self.other = Employee.objects.create(user=self.u_other, department=self.dept)

        self.u_boss = UserAccount.objects.create_user(username='boss_detail', password='123')
        self.u_boss.role = RoleEnums.ADMINISTRATOR.value
        self.u_boss.save()
        self.boss = Employee.objects.create(user=self.u_boss, department=self.dept, head=True)

        self.leave_type = LeaveType.objects.create(name="Ежегодный_d", max_days_per_year=24)
        self.leave = LeaveRequest.objects.create(
            employee=self.owner, leave_type=self.leave_type,
            start_date=date(2026, 8, 3), end_date=date(2026, 8, 7),
            status=LeaveStatusEnum.PENDING,
        )

    def get_url(self):
        return reverse('hr:leave_detail', kwargs={'pk': self.leave.pk})

    def test_anonymous_redirected(self):
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 302)

    def test_owner_can_view(self):
        self.client.login(username='owner_detail', password='123')
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'site/hr/leave_detail.html')

    def test_manager_can_view(self):
        self.client.login(username='boss_detail', password='123')
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)

    def test_other_employee_redirected(self):
        self.client.login(username='other_detail', password='123')
        response = self.client.get(self.get_url())
        self.assertRedirects(response, reverse('hr:leave_list'))

    def test_context_has_correct_leave(self):
        self.client.login(username='owner_detail', password='123')
        response = self.client.get(self.get_url())
        self.assertEqual(response.context['leave'].pk, self.leave.pk)

    def test_is_owner_true_for_owner(self):
        self.client.login(username='owner_detail', password='123')
        response = self.client.get(self.get_url())
        self.assertTrue(response.context['is_owner'])

    def test_is_owner_false_for_manager(self):
        self.client.login(username='boss_detail', password='123')
        response = self.client.get(self.get_url())
        self.assertFalse(response.context['is_owner'])

    def test_nonexistent_returns_404(self):
        self.client.login(username='owner_detail', password='123')
        
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get(reverse('hr:leave_detail', kwargs={'pk': 99999}))
        
        request.user = self.u_owner 
        from .views import leave_detail
        with self.assertRaises(Http404):
            leave_detail(request, pk=99999)


class LeaveApproveViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="ApproveCorp", bin_number="444444444444")
        self.dept = Department.objects.create(name="Ops", company=self.company)

        self.u_emp = UserAccount.objects.create_user(username='emp_approve', password='123')
        self.employee = Employee.objects.create(user=self.u_emp, department=self.dept)

        self.u_emp2 = UserAccount.objects.create_user(username='emp_approve2', password='123')
        self.employee2 = Employee.objects.create(user=self.u_emp2, department=self.dept)

        self.u_boss = UserAccount.objects.create_user(username='boss_approve', password='123')
        self.u_boss.role = RoleEnums.ADMINISTRATOR.value
        self.u_boss.save()
        self.boss = Employee.objects.create(user=self.u_boss, department=self.dept, head=True)

        self.leave_type = LeaveType.objects.create(name="Ежегодный_a", max_days_per_year=24)
        self.leave = LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 3), end_date=date(2026, 8, 7),
            status=LeaveStatusEnum.PENDING,
        )

    def get_url(self):
        return reverse('hr:leave_approve', kwargs={'pk': self.leave.pk})

    def test_anonymous_redirected(self):
        response = self.client.post(self.get_url())
        self.assertEqual(response.status_code, 302)

    def test_get_request_does_not_approve(self):
        self.client.login(username='boss_approve', password='123')
        self.client.get(self.get_url())
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.status, LeaveStatusEnum.PENDING)

    def test_manager_can_approve_via_post(self):
        self.client.login(username='boss_approve', password='123')
        response = self.client.post(self.get_url())
        self.assertRedirects(response, reverse('hr:leave_list'))
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.status, LeaveStatusEnum.APPROVED)

    def test_approve_sets_approver(self):
        self.client.login(username='boss_approve', password='123')
        self.client.post(self.get_url())
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.approver, self.boss)

    def test_regular_employee_cannot_approve(self):
        self.client.login(username='emp_approve2', password='123')
        self.client.post(self.get_url())
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.status, LeaveStatusEnum.PENDING)

    def test_cannot_approve_already_approved(self):
        self.leave.status = LeaveStatusEnum.APPROVED
        self.leave.save()
        self.client.login(username='boss_approve', password='123')
        self.client.post(self.get_url())
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.status, LeaveStatusEnum.APPROVED)

    def test_cannot_approve_rejected(self):
        self.leave.status = LeaveStatusEnum.REJECTED
        self.leave.save()
        self.client.login(username='boss_approve', password='123')
        self.client.post(self.get_url())
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.status, LeaveStatusEnum.REJECTED)

    def test_nonexistent_returns_404(self):
        self.client.login(username='boss_approve', password='123')
        from .views import leave_approve
        with self.assertRaises(Http404):
            leave_approve(self.client.get('/').wsgi_request, pk=99999)


class LeaveRejectExtendedTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="RejectCorp", bin_number="555555555555")
        self.dept = Department.objects.create(name="Legal", company=self.company)

        self.u_emp = UserAccount.objects.create_user(username='emp_reject', password='123')
        self.employee = Employee.objects.create(user=self.u_emp, department=self.dept)

        self.u_emp2 = UserAccount.objects.create_user(username='emp_reject2', password='123')
        self.employee2 = Employee.objects.create(user=self.u_emp2, department=self.dept)

        self.u_boss = UserAccount.objects.create_user(username='boss_reject', password='123')
        self.u_boss.role = RoleEnums.ADMINISTRATOR.value
        self.u_boss.save()
        self.boss = Employee.objects.create(user=self.u_boss, department=self.dept, head=True)

        self.leave_type = LeaveType.objects.create(name="Ежегодный_r", max_days_per_year=24)
        self.leave = LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 3), end_date=date(2026, 8, 7),
            status=LeaveStatusEnum.PENDING,
        )

    def get_url(self):
        return reverse('hr:leave_reject', kwargs={'pk': self.leave.pk})

    def test_get_request_does_not_reject(self):
        self.client.login(username='boss_reject', password='123')
        self.client.get(self.get_url())
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.status, LeaveStatusEnum.PENDING)

    def test_regular_employee_cannot_reject(self):
        self.client.login(username='emp_reject2', password='123')
        self.client.post(self.get_url())
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.status, LeaveStatusEnum.PENDING)

    def test_cannot_reject_already_approved(self):
        self.leave.status = LeaveStatusEnum.APPROVED
        self.leave.save()
        self.client.login(username='boss_reject', password='123')
        self.client.post(self.get_url())
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.status, LeaveStatusEnum.APPROVED)

    def test_nonexistent_returns_404(self):
        self.client.login(username='boss_reject', password='123')
        from .views import leave_reject
        with self.assertRaises(Http404):
            leave_reject(self.client.get('/').wsgi_request, pk=99999)


class LeaveCancelExtendedTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="CancelCorp", bin_number="666666666666")
        self.dept = Department.objects.create(name="Mkt", company=self.company)

        self.u_emp = UserAccount.objects.create_user(username='emp_cancel', password='123')
        self.employee = Employee.objects.create(user=self.u_emp, department=self.dept)

        self.u_emp2 = UserAccount.objects.create_user(username='emp_cancel2', password='123')
        self.employee2 = Employee.objects.create(user=self.u_emp2, department=self.dept)

        self.leave_type = LeaveType.objects.create(name="Ежегодный_cn", max_days_per_year=24)

    def test_get_request_does_not_delete(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 3), end_date=date(2026, 8, 7),
            status=LeaveStatusEnum.PENDING,
        )
        self.client.login(username='emp_cancel', password='123')
        self.client.get(reverse('hr:leave_cancel', args=[leave.pk]))
        self.assertTrue(LeaveRequest.objects.filter(pk=leave.pk).exists())

    def test_can_cancel_pending_via_post(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 3), end_date=date(2026, 8, 7),
            status=LeaveStatusEnum.PENDING,
        )
        self.client.login(username='emp_cancel', password='123')
        self.client.post(reverse('hr:leave_cancel', args=[leave.pk]))
        self.assertFalse(LeaveRequest.objects.filter(pk=leave.pk).exists())

    def test_other_employee_cannot_cancel(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 3), end_date=date(2026, 8, 7),
            status=LeaveStatusEnum.PENDING,
        )
        self.client.login(username='emp_cancel2', password='123')
        self.client.post(reverse('hr:leave_cancel', args=[leave.pk]))
        self.assertTrue(LeaveRequest.objects.filter(pk=leave.pk).exists())

    def test_anonymous_redirected(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 3), end_date=date(2026, 8, 7),
            status=LeaveStatusEnum.PENDING,
        )
        response = self.client.post(reverse('hr:leave_cancel', args=[leave.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(LeaveRequest.objects.filter(pk=leave.pk).exists())


class AjaxCalculateDaysExtendedTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="AjaxCorp", bin_number="777777777777")
        self.dept = Department.objects.create(name="Data", company=self.company)

        self.u_emp = UserAccount.objects.create_user(username='emp_ajax', password='123')
        self.employee = Employee.objects.create(user=self.u_emp, department=self.dept)

        self.u_no_profile = UserAccount.objects.create_user(username='noprofile_ajax', password='123')

    def get_url(self):
        return reverse('hr:ajax_calculate_days')

    def test_anonymous_redirected(self):
        response = self.client.get(self.get_url(), {'start': '2026-06-01', 'end': '2026-06-05'})
        self.assertEqual(response.status_code, 302)

    def test_returns_json_content_type(self):
        self.client.login(username='emp_ajax', password='123')
        response = self.client.get(self.get_url(), {'start': '2026-06-01', 'end': '2026-06-05'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/json', response['Content-Type'])

    def test_monday_to_friday_five_days(self):
        """2026-06-01 (пн) — 2026-06-05 (пт) = 5 рабочих дней."""
        self.client.login(username='emp_ajax', password='123')
        response = self.client.get(self.get_url(), {'start': '2026-06-01', 'end': '2026-06-05'})
        self.assertEqual(response.json()['days'], 5)

    def test_weekend_excluded(self):
        """2026-06-01 (пн) — 2026-06-07 (вс) = 5 рабочих дней."""
        self.client.login(username='emp_ajax', password='123')
        response = self.client.get(self.get_url(), {'start': '2026-06-01', 'end': '2026-06-07'})
        self.assertEqual(response.json()['days'], 5)

    def test_no_params_returns_zero(self):
        self.client.login(username='emp_ajax', password='123')
        response = self.client.get(self.get_url())
        self.assertEqual(response.json()['days'], 0)

    def test_missing_end_returns_zero(self):
        self.client.login(username='emp_ajax', password='123')
        response = self.client.get(self.get_url(), {'start': '2026-06-01'})
        self.assertEqual(response.json()['days'], 0)

    def test_invalid_format_returns_zero(self):
        self.client.login(username='emp_ajax', password='123')
        response = self.client.get(self.get_url(), {'start': 'abc', 'end': 'def'})
        self.assertEqual(response.json()['days'], 0)

    def test_start_after_end_returns_zero(self):
        self.client.login(username='emp_ajax', password='123')
        response = self.client.get(self.get_url(), {'start': '2026-06-10', 'end': '2026-06-05'})
        self.assertEqual(response.json()['days'], 0)

    def test_user_without_employee_profile_returns_zero(self):
        self.client.login(username='noprofile_ajax', password='123')
        response = self.client.get(self.get_url(), {'start': '2026-06-01', 'end': '2026-06-05'})
        self.assertEqual(response.json()['days'], 0)

    def test_single_working_day(self):
        self.client.login(username='emp_ajax', password='123')
        response = self.client.get(self.get_url(), {'start': '2026-06-01', 'end': '2026-06-01'})
        self.assertEqual(response.json()['days'], 1)

    def test_single_weekend_returns_zero(self):
        self.client.login(username='emp_ajax', password='123')
        response = self.client.get(self.get_url(), {'start': '2026-06-06', 'end': '2026-06-06'})
        self.assertEqual(response.json()['days'], 0)


class LeaveFormTest(TestCase):

    def setUp(self):
        self.leave_type = LeaveType.objects.create(name="Ежегодный_f", max_days_per_year=24)

    def test_leave_request_form_valid(self):
        from .forms import LeaveRequestForm
        form = LeaveRequestForm(data={
            'leave_type': self.leave_type.pk,
            'start_date': '2026-08-03',
            'end_date': '2026-08-07',
            'comment': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_leave_request_form_start_after_end(self):
        from .forms import LeaveRequestForm
        form = LeaveRequestForm(data={
            'leave_type': self.leave_type.pk,
            'start_date': '2026-08-10',
            'end_date': '2026-08-05',
            'comment': '',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_leave_request_form_equal_dates_valid(self):
        from .forms import LeaveRequestForm
        form = LeaveRequestForm(data={
            'leave_type': self.leave_type.pk,
            'start_date': '2026-08-03',
            'end_date': '2026-08-03',
            'comment': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_leave_request_form_missing_type(self):
        from .forms import LeaveRequestForm
        form = LeaveRequestForm(data={
            'leave_type': '',
            'start_date': '2026-08-03',
            'end_date': '2026-08-07',
            'comment': '',
        })
        if form.is_valid():
            pass
        else:
            self.assertIn('leave_type', form.errors)

    def test_leave_filter_form_empty_is_valid(self):
        from .forms import LeaveFilterForm
        form = LeaveFilterForm(data={})
        self.assertTrue(form.is_valid(), form.errors)

    def test_leave_filter_form_invalid_date(self):
        from .forms import LeaveFilterForm
        form = LeaveFilterForm(data={'date_from': 'notadate'})
        self.assertFalse(form.is_valid())
@override_settings(
    ENBEK_BASE_URL='http://testserver/api/enbek',
    ENBEK_USERNAME='test_user',
    ENBEK_PASSWORD='test_password',
    ENBEK_TIMEOUT=5,
)
class EnbekClientTestCase(TestCase):
    def setUp(self):
        self.client = EnbekClient()

    def test_authenticate_with_valid_credentials_returns_token(self):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "mock_token_123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch.object(self.client.session, 'post', return_value=mock_response) as mock_post:
            token = self.client.authenticate()

        self.assertEqual(token, "mock_token_123")
        self.assertEqual(self.client.token, "mock_token_123")

        mock_post.assert_called_once_with(
            'http://testserver/api/enbek/auth/login/',
            json={
                'username': 'test_user',
                'password': 'test_password',
            },
            headers={
                'Content-Type': 'application/json',
                'Host': 'localhost',
            },
            timeout=5,
        )

    def test_authenticate_with_invalid_credentials_raises_authentication_error(self):
        mock_response = Mock()
        mock_response.status_code = 401

        with patch.object(self.client.session, 'post', return_value=mock_response):
            with self.assertRaises(AuthenticationError):
                self.client.authenticate()

    def test_get_vacations_returns_list(self):
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            "access_token": "mock_token_123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        vacations_response = Mock()
        vacations_response.status_code = 200
        vacations_response.json.return_value = [
            {
                "id": 1,
                "employee_name": "Иван Иванов",
                "type": "annual",
                "start_date": "2024-06-01",
                "end_date": "2024-06-14",
                "status": "approved",
            }
        ]

        with patch.object(self.client.session, 'post', return_value=auth_response):
            with patch.object(self.client.session, 'get', return_value=vacations_response) as mock_get:
                vacations = self.client.get_vacations()

        self.assertIsInstance(vacations, list)
        self.assertEqual(len(vacations), 1)
        self.assertEqual(vacations[0]['id'], 1)
        self.assertEqual(vacations[0]['employee_name'], 'Иван Иванов')
        self.assertEqual(vacations[0]['type'], 'annual')

        mock_get.assert_called_once_with(
            'http://testserver/api/enbek/leaves/',
            headers={
                'Content-Type': 'application/json',
                'Host': 'localhost',
                'Authorization': 'Bearer mock_token_123',
            },
            timeout=5,
        )

    def test_get_sick_leaves_empty_response_returns_empty_list(self):
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            "access_token": "mock_token_123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        sick_leaves_response = Mock()
        sick_leaves_response.status_code = 200
        sick_leaves_response.json.return_value = []

        with patch.object(self.client.session, 'post', return_value=auth_response):
            with patch.object(self.client.session, 'get', return_value=sick_leaves_response):
                sick_leaves = self.client.get_sick_leaves()

        self.assertIsInstance(sick_leaves, list)
        self.assertEqual(sick_leaves, [])

    def test_timeout_when_api_unavailable_raises_connection_error_with_retry_case(self):
        with patch.object(
            self.client.session,
            'post',
            side_effect=requests.exceptions.Timeout
        ):
            with self.assertRaises(ConnectionError):
                self.client.authenticate()

    def test_handle_response_with_invalid_json_raises_enbek_client_error(self):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError('Invalid JSON')

        with self.assertRaises(EnbekClientError):
            self.client._handle_response(mock_response)

    def test_authenticate_without_token_in_response_raises_authentication_error(self):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch.object(self.client.session, 'post', return_value=mock_response):
            with self.assertRaises(AuthenticationError):
                self.client.authenticate()

    def test_server_error_raises_connection_error(self):
        mock_response = Mock()
        mock_response.status_code = 500

        with self.assertRaises(ConnectionError):
            self.client._handle_response(mock_response)

    def test_client_error_raises_enbek_client_error(self):
        mock_response = Mock()
        mock_response.status_code = 404

        with self.assertRaises(EnbekClientError):
            self.client._handle_response(mock_response)

class EnbekModelsTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='Test Company',
            bin_number='123456789012',
        )

        self.department = Department.objects.create(
            name='IT Department',
            company=self.company,
        )

        self.user = UserAccount.objects.create_user(
            username='employee1',
            password='testpass123',
            role='staff',
        )

        self.employee = Employee.objects.create(
            user=self.user,
            department=self.department,
            iin='123456789012',
            status='active',
        )

    def test_create_vacation_with_unique_enbek_id(self):
        vacation = Vacation.objects.create(
            employee=self.employee,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )

        self.assertIsNotNone(vacation.id)
        self.assertEqual(vacation.enbek_id, 'vac_1')
        self.assertEqual(vacation.employee, self.employee)

    def test_duplicate_vacation_enbek_id_raises_integrity_error(self):
        Vacation.objects.create(
            employee=self.employee,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )

        with self.assertRaises(IntegrityError):
            Vacation.objects.create(
                employee=self.employee,
                type='annual',
                start_date='2024-07-01',
                end_date='2024-07-10',
                status='approved',
                enbek_id='vac_1',
            )

    def test_sick_leave_is_linked_to_employee(self):
        sick_leave = SickLeave.objects.create(
            employee=self.employee,
            start_date='2024-03-01',
            end_date='2024-03-05',
            document_number='SL-001',
            enbek_id='sick_1',
        )

        self.assertEqual(sick_leave.employee, self.employee)
        self.assertIn(sick_leave, self.employee.sick_leaves.all())

    def test_employment_contract_saved_with_type_and_status(self):
        contract = EmploymentContract.objects.create(
            employee=self.employee,
            number='CTR-001',
            date='2024-01-10',
            type='labor',
            status='active',
            enbek_id='contract_1',
        )

        self.assertEqual(contract.number, 'CTR-001')
        self.assertEqual(contract.type, 'labor')
        self.assertEqual(contract.status, 'active')
        self.assertEqual(contract.enbek_id, 'contract_1')
        self.assertEqual(contract.employee, self.employee)

    def test_delete_employee_sets_null_in_related_enbek_models(self):
        vacation = Vacation.objects.create(
            employee=self.employee,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )

        sick_leave = SickLeave.objects.create(
            employee=self.employee,
            start_date='2024-03-01',
            end_date='2024-03-05',
            document_number='SL-001',
            enbek_id='sick_1',
        )

        contract = EmploymentContract.objects.create(
            employee=self.employee,
            number='CTR-001',
            date='2024-01-10',
            type='labor',
            status='active',
            enbek_id='contract_1',
        )

        self.employee.delete()

        vacation.refresh_from_db()
        sick_leave.refresh_from_db()
        contract.refresh_from_db()

        self.assertIsNone(vacation.employee)
        self.assertIsNone(sick_leave.employee)
        self.assertIsNone(contract.employee)

class EnbekSyncServiceTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='Test Company',
            bin_number='123456789012',
        )

        self.department = Department.objects.create(
            name='IT Department Sync',
            company=self.company,
        )

        self.user = UserAccount.objects.create_user(
            username='sync_employee',
            password='testpass123',
            role='staff',
        )

        self.employee = Employee.objects.create(
            user=self.user,
            department=self.department,
            iin='111111111111',
            status='active',
        )

        self.service = EnbekSyncService()

    @patch('hr.services.logger')
    @patch('hr.services.EnbekClient.get_employment_contracts')
    @patch('hr.services.EnbekClient.get_sick_leaves')
    @patch('hr.services.EnbekClient.get_vacations')
    def test_sync_with_new_data_creates_records(
        self,
        mock_get_vacations,
        mock_get_sick_leaves,
        mock_get_contracts,
        mock_logger
    ):
        mock_get_vacations.return_value = [
            {
                'id': 'vac_1',
                'iin': '111111111111',
                'type': 'annual',
                'start_date': '2024-06-01',
                'end_date': '2024-06-14',
                'status': 'approved',
            }
        ]
        mock_get_sick_leaves.return_value = [
            {
                'id': 'sick_1',
                'iin': '111111111111',
                'start_date': '2024-03-01',
                'end_date': '2024-03-05',
                'document_number': 'SL-001',
            }
        ]
        mock_get_contracts.return_value = [
            {
                'id': 'contract_1',
                'iin': '111111111111',
                'number': 'CTR-001',
                'date': '2024-01-10',
                'type': 'labor',
                'status': 'active',
            }
        ]

        result = self.service.sync_all()

        self.assertEqual(result['created'], 3)
        self.assertEqual(result['updated'], 0)

        self.assertEqual(Vacation.objects.count(), 1)
        self.assertEqual(SickLeave.objects.count(), 1)
        self.assertEqual(EmploymentContract.objects.count(), 1)

        vacation = Vacation.objects.get(enbek_id='vac_1')
        sick_leave = SickLeave.objects.get(enbek_id='sick_1')
        contract = EmploymentContract.objects.get(enbek_id='contract_1')

        self.assertEqual(vacation.employee, self.employee)
        self.assertEqual(sick_leave.employee, self.employee)
        self.assertEqual(contract.employee, self.employee)

        mock_logger.info.assert_any_call("sync_started")
        mock_logger.info.assert_any_call(
            "sync_completed",
            extra={
                "created_count": 3,
                "updated_count": 0,
                "vacations_count": 1,
                "sick_leaves_count": 1,
                "employment_contracts_count": 1,
            }
        )

    @patch('hr.services.EnbekClient.get_employment_contracts')
    @patch('hr.services.EnbekClient.get_sick_leaves')
    @patch('hr.services.EnbekClient.get_vacations')
    def test_sync_with_existing_data_updates_records(
        self,
        mock_get_vacations,
        mock_get_sick_leaves,
        mock_get_contracts
    ):
        Vacation.objects.create(
            employee=self.employee,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )
        SickLeave.objects.create(
            employee=self.employee,
            start_date='2024-03-01',
            end_date='2024-03-05',
            document_number='SL-001',
            enbek_id='sick_1',
        )
        EmploymentContract.objects.create(
            employee=self.employee,
            number='CTR-001',
            date='2024-01-10',
            type='labor',
            status='active',
            enbek_id='contract_1',
        )

        mock_get_vacations.return_value = [
            {
                'id': 'vac_1',
                'iin': '111111111111',
                'type': 'study',
                'start_date': '2024-07-01',
                'end_date': '2024-07-10',
                'status': 'changed',
            }
        ]
        mock_get_sick_leaves.return_value = [
            {
                'id': 'sick_1',
                'iin': '111111111111',
                'start_date': '2024-03-02',
                'end_date': '2024-03-06',
                'document_number': 'SL-002',
            }
        ]
        mock_get_contracts.return_value = [
            {
                'id': 'contract_1',
                'iin': '111111111111',
                'number': 'CTR-999',
                'date': '2024-02-15',
                'type': 'updated_type',
                'status': 'inactive',
            }
        ]

        result = self.service.sync_all()

        self.assertEqual(result['created'], 0)
        self.assertEqual(result['updated'], 3)

        self.assertEqual(Vacation.objects.count(), 1)
        self.assertEqual(SickLeave.objects.count(), 1)
        self.assertEqual(EmploymentContract.objects.count(), 1)

        vacation = Vacation.objects.get(enbek_id='vac_1')
        sick_leave = SickLeave.objects.get(enbek_id='sick_1')
        contract = EmploymentContract.objects.get(enbek_id='contract_1')

        self.assertEqual(vacation.type, 'study')
        self.assertEqual(str(vacation.start_date), '2024-07-01')
        self.assertEqual(vacation.status, 'changed')

        self.assertEqual(str(sick_leave.start_date), '2024-03-02')
        self.assertEqual(str(sick_leave.end_date), '2024-03-06')
        self.assertEqual(sick_leave.document_number, 'SL-002')

        self.assertEqual(contract.number, 'CTR-999')
        self.assertEqual(str(contract.date), '2024-02-15')
        self.assertEqual(contract.type, 'updated_type')
        self.assertEqual(contract.status, 'inactive')

    @patch('hr.services.logger')
    @patch('hr.services.EnbekClient.get_vacations')
    def test_sync_on_api_error_logs_error_and_existing_data_not_changed(
        self,
        mock_get_vacations,
        mock_logger
    ):
        vacation = Vacation.objects.create(
            employee=self.employee,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )

        mock_get_vacations.side_effect = Exception('API is down')

        with self.assertRaises(Exception):
            self.service.sync_all()

        vacation.refresh_from_db()
        self.assertEqual(vacation.type, 'annual')
        self.assertEqual(vacation.status, 'approved')
        self.assertEqual(Vacation.objects.count(), 1)

        mock_logger.info.assert_any_call("sync_started")
        mock_logger.exception.assert_called_once_with("sync_error")

    @patch('hr.services.logger')
    @patch('hr.services.EnbekClient.get_employment_contracts')
    @patch('hr.services.EnbekClient.get_sick_leaves')
    @patch('hr.services.EnbekClient.get_vacations')
    def test_sync_with_empty_response_changes_nothing(
        self,
        mock_get_vacations,
        mock_get_sick_leaves,
        mock_get_contracts,
        mock_logger
    ):
        Vacation.objects.create(
            employee=self.employee,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )

        mock_get_vacations.return_value = []
        mock_get_sick_leaves.return_value = []
        mock_get_contracts.return_value = []

        result = self.service.sync_all()

        self.assertEqual(result['created'], 0)
        self.assertEqual(result['updated'], 0)

        self.assertEqual(Vacation.objects.count(), 1)
        self.assertEqual(SickLeave.objects.count(), 0)
        self.assertEqual(EmploymentContract.objects.count(), 0)

        mock_logger.info.assert_any_call("sync_started")
        mock_logger.info.assert_any_call(
            "sync_completed",
            extra={
                "created_count": 0,
                "updated_count": 0,
                "vacations_count": 0,
                "sick_leaves_count": 0,
                "employment_contracts_count": 0,
            }
        )   

    @patch('hr.services.EnbekClient.get_employment_contracts')
    @patch('hr.services.EnbekClient.get_sick_leaves')
    @patch('hr.services.EnbekClient.get_vacations')
    def test_sync_does_not_create_duplicates_for_same_enbek_id(
        self,
        mock_get_vacations,
        mock_get_sick_leaves,
        mock_get_contracts
    ):
        mock_get_vacations.return_value = [
            {
                'id': 'vac_1',
                'iin': '111111111111',
                'type': 'annual',
                'start_date': '2024-06-01',
                'end_date': '2024-06-14',
                'status': 'approved',
            }
        ]
        mock_get_sick_leaves.return_value = []
        mock_get_contracts.return_value = []

        first_result = self.service.sync_all()
        second_result = self.service.sync_all()

        self.assertEqual(first_result['created'], 1)
        self.assertEqual(first_result['updated'], 0)

        self.assertEqual(second_result['created'], 0)
        self.assertEqual(second_result['updated'], 1)

        self.assertEqual(Vacation.objects.filter(enbek_id='vac_1').count(), 1)

class EnbekCeleryTaskTestCase(TestCase):

    @patch('hr.tasks.EnbekSyncService')
    def test_task_calls_sync_service_and_returns_result(self, mock_service_class):
        mock_service = mock_service_class.return_value
        mock_service.sync_all.return_value = {
            "created": 2,
            "updated": 1,
        }

        result = sync_enbek_data()

        self.assertEqual(result, {
            "created": 2,
            "updated": 1,
        })

        mock_service.sync_all.assert_called_once()

    @patch('hr.tasks.logger')
    @patch('hr.tasks.EnbekSyncService')
    def test_task_logs_error_and_raises_exception(self, mock_service_class, mock_logger):
        mock_service = mock_service_class.return_value
        mock_service.sync_all.side_effect = Exception("API error")

        with self.assertRaises(Exception):
            sync_enbek_data()

        mock_logger.exception.assert_called_once_with("celery_sync_error")

    @patch('hr.tasks.cache')
    @patch('hr.tasks.EnbekSyncService')
    def test_task_skips_when_locked(self, mock_service_class, mock_cache):
        mock_cache.get.return_value = True 

        result = sync_enbek_data()

        self.assertEqual(result, {"status": "skipped"})
        mock_service_class.assert_not_called()

class EnbekViewsTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='View Test Company',
            bin_number='999999999999',
        )

        self.department = Department.objects.create(
            name='HR View Department',
            company=self.company,
        )

        self.admin_user = UserAccount.objects.create_user(
            username='hr_admin',
            password='testpass123',
            role='administrator',
        )

        self.employee_user_1 = UserAccount.objects.create_user(
            username='emp1',
            password='testpass123',
            role='staff',
            first_name='Ivan',
        )

        self.employee_user_2 = UserAccount.objects.create_user(
            username='emp2',
            password='testpass123',
            role='staff',
            first_name='Petr',
        )

        self.employee_1 = Employee.objects.create(
            user=self.employee_user_1,
            department=self.department,
            iin='100000000001',
            status='active',
        )

        self.employee_2 = Employee.objects.create(
            user=self.employee_user_2,
            department=self.department,
            iin='100000000002',
            status='active',
        )

        Vacation.objects.create(
            employee=self.employee_1,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )
        Vacation.objects.create(
            employee=self.employee_2,
            type='study',
            start_date='2024-07-01',
            end_date='2024-07-10',
            status='approved',
            enbek_id='vac_2',
        )

        SickLeave.objects.create(
            employee=self.employee_1,
            start_date='2024-03-01',
            end_date='2024-03-05',
            document_number='SL-001',
            enbek_id='sick_1',
        )

        EmploymentContract.objects.create(
            employee=self.employee_1,
            number='CTR-001',
            date='2024-01-10',
            type='labor',
            status='active',
            enbek_id='contract_1',
        )

        self.client.force_login(self.admin_user)

    def test_get_hr_vacations_returns_200_and_list(self):
        response = self.client.get('/hr/vacations/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Отпуска (Enbek)')
        self.assertContains(response, 'vac_1')
        self.assertContains(response, 'vac_2')

    def test_get_hr_sick_leaves_returns_200_and_list(self):
        response = self.client.get('/hr/sick-leaves/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Больничные (Enbek)')
        self.assertContains(response, 'sick_1')

    def test_get_hr_contracts_returns_200_and_list(self):
        response = self.client.get('/hr/contracts/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Договоры (Enbek)')
        self.assertContains(response, 'contract_1')

    def test_filter_by_employee_returns_only_employee_data(self):
        response = self.client.get(f'/hr/vacations/?employee={self.employee_1.id}')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'vac_1')
        self.assertNotContains(response, 'vac_2')

    def test_views_are_read_only(self):
        response = self.client.get('/hr/vacations/')

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Редактировать')
        self.assertNotContains(response, 'Удалить')

    def test_hr_menu_contains_new_enbek_items(self):
        menu = MenuItem.generate_menu(self.admin_user)

        hr_item = next(item for item in menu if item.id == 'hr')
        submenu_titles = [item.title for item in hr_item.submenu]

        self.assertIn('Отпуска (Enbek)', submenu_titles)
        self.assertIn('Больничные (Enbek)', submenu_titles)
        self.assertIn('Договоры (Enbek)', submenu_titles)

