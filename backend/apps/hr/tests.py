from django.test import TestCase
from datetime import date
from .models import LeaveRequest, LeaveType, WorkCalendar, Company, Position
from .enums import LeaveStatusEnum, DayTypeEnum
try:
    from account.models import Employee, UserAccount, Department
except ImportError:
    from apps.account.models import Employee, UserAccount, Department

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