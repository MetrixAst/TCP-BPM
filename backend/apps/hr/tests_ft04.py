from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company, OfficeQRPoint, AttendanceRecord
from hr.enums import CheckInEnum
from ecopark.models import (
    EcoObject, ChecklistTemplate, RoundPoint,
    Route, RoutePoint, PlannedRound
)


def make_setup():
    company = Company.objects.create(name='FT04 Co', bin_number='444555666777')
    dept = Department.objects.create(name='FT04 Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_ft04', password='pass', role='administrator')
    emp_user = UserAccount.objects.create_user(username='emp_ft04', password='pass', role='staff')
    other = UserAccount.objects.create_user(username='other_ft04', password='pass', role='staff')
    employee = Employee.objects.create(user=emp_user, department=dept, status='active')
    Employee.objects.create(user=other, department=dept, status='active')
    office_qr = OfficeQRPoint.objects.create(name='FT04 Вход', created_by=admin)

    eco = EcoObject.objects.create(name='FT04 Eco')
    template = ChecklistTemplate.objects.create(name='FT04 Template', created_by=admin)
    point = RoundPoint.objects.create(name='FT04 Точка', eco_object=eco, checklist=template, created_by=admin)
    route = Route.objects.create(name='FT04 Маршрут', assigned_employee=emp_user, created_by=admin)
    RoutePoint.objects.create(route=route, point=point, order=1)
    now = timezone.now()
    planned = PlannedRound.objects.create(
        route=route,
        assigned_to=emp_user,
        planned_start=now - timedelta(hours=1),
        planned_end=now + timedelta(hours=1),
    )
    return admin, emp_user, other, employee, office_qr, point, planned


class MigrationsRegressionTest(TestCase):

    def test_office_qr_point_exists(self):
        admin = UserAccount.objects.create_user(username='admin_mig', password='pass', role='administrator')
        point = OfficeQRPoint.objects.create(name='Тест', created_by=admin)
        self.assertIsNotNone(point.public_id)

    def test_planned_round_no_duplicate(self):
        admin = UserAccount.objects.create_user(username='admin_mig2', password='pass', role='administrator')
        emp = UserAccount.objects.create_user(username='emp_mig2', password='pass', role='staff')
        eco = EcoObject.objects.create(name='Mig Eco')
        template = ChecklistTemplate.objects.create(name='Mig Template', created_by=admin)
        point = RoundPoint.objects.create(name='Mig Point', eco_object=eco, checklist=template, created_by=admin)
        route = Route.objects.create(name='Mig Route', assigned_employee=emp, created_by=admin)
        RoutePoint.objects.create(route=route, point=point, order=1)
        now = timezone.now()
        PlannedRound.objects.create(
            route=route,
            assigned_to=emp,
            planned_start=now,
            planned_end=now + timedelta(hours=2),
        )
        with self.assertRaises(Exception):
            PlannedRound.objects.create(
                route=route,
                assigned_to=emp,
                planned_start=now,
                planned_end=now + timedelta(hours=2),
            )

    def test_historical_attendance_preserved(self):
        company = Company.objects.create(name='Hist Co', bin_number='888999111222')
        dept = Department.objects.create(name='Hist Dept', company=company)
        emp_user = UserAccount.objects.create_user(username='emp_hist', password='pass', role='staff')
        employee = Employee.objects.create(user=emp_user, department=dept, status='active')
        record = AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                employee=employee,
                event_type=CheckInEnum.DAY_START,
                timestamp=timezone.now() - timedelta(days=30),
                source='face',
            )
        ])[0]
        self.assertTrue(AttendanceRecord.objects.filter(pk=record.pk).exists())


class RBACRegressionTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.emp, self.other, self.employee, \
            self.office_qr, self.point, self.planned = make_setup()

    def test_office_qr_requires_auth(self):
        r = self.client.get(f'/hr/attendance/office-qr/{self.office_qr.public_id}/')
        self.assertIn(r.status_code, [302, 403])

    def test_office_qr_get_no_record(self):
        self.client.force_login(self.emp)
        count = AttendanceRecord.objects.count()
        self.client.get(f'/hr/attendance/office-qr/{self.office_qr.public_id}/')
        self.assertEqual(AttendanceRecord.objects.count(), count)

    def test_rounds_today_only_own(self):
        self.client.force_authenticate(user=self.other)
        r = self.client.get('/api/v1/mobile/rounds/today/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 0)

    def test_round_detail_foreign_user_403(self):
        self.client.force_authenticate(user=self.other)
        r = self.client.get(f'/api/v1/mobile/rounds/{self.planned.pk}/')
        self.assertEqual(r.status_code, 403)


class IdempotencyRegressionTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.emp, self.other, self.employee, \
            self.office_qr, self.point, self.planned = make_setup()
        self.client.force_login(self.emp)

    def test_office_qr_idempotency(self):
        self.client.post(f'/hr/attendance/office-qr/{self.office_qr.public_id}/checkin/')
        self.client.post(f'/hr/attendance/office-qr/{self.office_qr.public_id}/checkin/')
        count = AttendanceRecord.objects.filter(
            employee=self.employee,
            event_type=CheckInEnum.DAY_START,
        ).count()
        self.assertEqual(count, 1)

    def test_office_qr_reissue_old_invalid(self):
        old_id = self.office_qr.public_id
        self.office_qr.reissue()
        r = self.client.get(f'/hr/attendance/office-qr/{old_id}/')
        self.assertEqual(r.status_code, 404)