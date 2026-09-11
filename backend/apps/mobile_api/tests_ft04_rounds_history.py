from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company
from ecopark.models import (
    EcoObject, ChecklistTemplate, RoundPoint, Route, RoutePoint, PlannedRound,
)


def make_setup():
    company = Company.objects.create(name='FT04H Co', bin_number='333444555666')
    dept = Department.objects.create(name='FT04H Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_ft04h', password='pass', role='administrator')
    emp_user = UserAccount.objects.create_user(username='emp_ft04h', password='pass', role='staff')
    other_user = UserAccount.objects.create_user(username='other_ft04h', password='pass', role='staff')
    Employee.objects.create(user=emp_user, department=dept, status='active')
    Employee.objects.create(user=other_user, department=dept, status='active')

    eco_obj = EcoObject.objects.create(name='FT04H Eco')
    template = ChecklistTemplate.objects.create(name='FT04H Template', created_by=admin)
    point = RoundPoint.objects.create(name='FT04H Точка', eco_object=eco_obj, checklist=template, created_by=admin)
    route = Route.objects.create(name='FT04H Маршрут', assigned_employee=emp_user, created_by=admin)
    RoutePoint.objects.create(route=route, point=point, order=1)

    return admin, emp_user, other_user, route


class RoundsHistoryTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.emp_user, self.other_user, self.route = make_setup()
        self.client.force_authenticate(user=self.emp_user)

    def test_today_pending_excluded_from_history(self):
        now = timezone.now()
        PlannedRound.objects.create(
            route=self.route, assigned_to=self.emp_user,
            planned_start=now, planned_end=now + timedelta(hours=2),
            status=PlannedRound.STATUS_PENDING,
        )
        r = self.client.get('/api/v1/mobile/rounds/history/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 0)

    def test_past_round_included(self):
        yesterday = timezone.now() - timedelta(days=1)
        PlannedRound.objects.create(
            route=self.route, assigned_to=self.emp_user,
            planned_start=yesterday, planned_end=yesterday + timedelta(hours=2),
            status=PlannedRound.STATUS_MISSED,
        )
        r = self.client.get('/api/v1/mobile/rounds/history/')
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]['status'], 'missed')

    def test_today_completed_included(self):
        now = timezone.now()
        PlannedRound.objects.create(
            route=self.route, assigned_to=self.emp_user,
            planned_start=now, planned_end=now + timedelta(hours=2),
            status=PlannedRound.STATUS_COMPLETED,
            completed_at=now,
        )
        r = self.client.get('/api/v1/mobile/rounds/history/')
        self.assertEqual(len(r.data), 1)
        self.assertIsNotNone(r.data[0]['completed_at'])

    def test_only_own_rounds_returned(self):
        yesterday = timezone.now() - timedelta(days=1)
        PlannedRound.objects.create(
            route=self.route, assigned_to=self.other_user,
            planned_start=yesterday, planned_end=yesterday + timedelta(hours=2),
            status=PlannedRound.STATUS_MISSED,
        )
        r = self.client.get('/api/v1/mobile/rounds/history/')
        self.assertEqual(len(r.data), 0)

    def test_ordered_newest_first(self):
        base = timezone.now() - timedelta(days=5)
        older = PlannedRound.objects.create(
            route=self.route, assigned_to=self.emp_user,
            planned_start=base, planned_end=base + timedelta(hours=2),
            status=PlannedRound.STATUS_MISSED,
        )
        newer = PlannedRound.objects.create(
            route=self.route, assigned_to=self.emp_user,
            planned_start=base + timedelta(days=2), planned_end=base + timedelta(days=2, hours=2),
            status=PlannedRound.STATUS_MISSED,
        )
        r = self.client.get('/api/v1/mobile/rounds/history/')
        self.assertEqual(r.data[0]['id'], newer.pk)
        self.assertEqual(r.data[1]['id'], older.pk)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        r = self.client.get('/api/v1/mobile/rounds/history/')
        self.assertEqual(r.status_code, 401)
