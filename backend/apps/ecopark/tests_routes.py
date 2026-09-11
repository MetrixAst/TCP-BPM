from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta

from account.models import UserAccount, Employee, Department
from hr.models import Company
from ecopark.models import (
    EcoObject, RoundPoint, ChecklistTemplate,
    Route, RoutePoint, RouteSchedule, PlannedRound
)


def make_setup():
    company = Company.objects.create(name='Routes Co', bin_number='999888777666')
    dept = Department.objects.create(name='Routes Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_rt', password='pass', role='administrator')
    emp1 = UserAccount.objects.create_user(username='emp1_rt', password='pass', role='staff')
    emp2 = UserAccount.objects.create_user(username='emp2_rt', password='pass', role='staff')
    Employee.objects.create(user=emp1, department=dept, status='active')
    Employee.objects.create(user=emp2, department=dept, status='active')

    eco_obj = EcoObject.objects.create(name='Корпус А')
    template = ChecklistTemplate.objects.create(name='Шаблон', created_by=admin)
    point1 = RoundPoint.objects.create(name='Точка 1', eco_object=eco_obj, checklist=template, created_by=admin)
    point2 = RoundPoint.objects.create(name='Точка 2', eco_object=eco_obj, checklist=template, created_by=admin)

    route = Route.objects.create(
        name='Маршрут А',
        assigned_employee=emp1,
        created_by=admin,
    )
    RoutePoint.objects.create(route=route, point=point1, order=1)
    RoutePoint.objects.create(route=route, point=point2, order=2)

    return admin, emp1, emp2, route, point1, point2, dept


class RouteModelTest(TestCase):

    def setUp(self):
        self.admin, self.emp1, self.emp2, self.route, self.point1, self.point2, self.dept = make_setup()

    def test_route_has_points_in_order(self):
        points = self.route.route_points.order_by('order')
        self.assertEqual(points.count(), 2)
        self.assertEqual(points.first().point, self.point1)

    def test_get_current_assignee_returns_employee(self):
        assignee = self.route.get_current_assignee()
        self.assertEqual(assignee, self.emp1)

    def test_get_current_assignee_returns_substitute_in_period(self):
        now = timezone.now()
        self.route.substitute_employee = self.emp2
        self.route.substitute_from = now - timedelta(hours=1)
        self.route.substitute_to = now + timedelta(hours=1)
        self.route.save()
        assignee = self.route.get_current_assignee()
        self.assertEqual(assignee, self.emp2)

    def test_get_current_assignee_returns_main_outside_substitute_period(self):
        now = timezone.now()
        self.route.substitute_employee = self.emp2
        self.route.substitute_from = now - timedelta(days=2)
        self.route.substitute_to = now - timedelta(days=1)
        self.route.save()
        assignee = self.route.get_current_assignee()
        self.assertEqual(assignee, self.emp1)

    def test_no_duplicate_points_in_route(self):
        from django.db import IntegrityError
        with self.assertRaises(Exception):
            RoutePoint.objects.create(route=self.route, point=self.point1, order=3)


class PlannedRoundTest(TestCase):

    def setUp(self):
        self.admin, self.emp1, self.emp2, self.route, self.point1, self.point2, self.dept = make_setup()

    def test_create_planned_round(self):
        now = timezone.now()
        planned = PlannedRound.objects.create(
            route=self.route,
            assigned_to=self.emp1,
            planned_start=now,
            planned_end=now + timedelta(hours=2),
        )
        self.assertEqual(planned.status, PlannedRound.STATUS_PENDING)
        self.assertFalse(planned.is_overdue)

    def test_overdue_detection(self):
        now = timezone.now()
        planned = PlannedRound.objects.create(
            route=self.route,
            assigned_to=self.emp1,
            planned_start=now - timedelta(hours=3),
            planned_end=now - timedelta(hours=1),
        )
        self.assertTrue(planned.is_overdue)

    def test_no_duplicate_planned_rounds(self):
        now = timezone.now()
        PlannedRound.objects.create(
            route=self.route,
            assigned_to=self.emp1,
            planned_start=now,
            planned_end=now + timedelta(hours=2),
        )
        from django.db import IntegrityError
        with self.assertRaises(Exception):
            PlannedRound.objects.create(
                route=self.route,
                assigned_to=self.emp1,
                planned_start=now,
                planned_end=now + timedelta(hours=2),
            )

    def test_total_points_count(self):
        now = timezone.now()
        planned = PlannedRound.objects.create(
            route=self.route,
            assigned_to=self.emp1,
            planned_start=now,
            planned_end=now + timedelta(hours=2),
        )
        self.assertEqual(planned.total_points_count(), 2)


class MyPlannedRoundsViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, self.emp1, self.emp2, self.route, self.point1, self.point2, self.dept = make_setup()

    def test_employee_sees_only_own_rounds(self):
        now = timezone.now()
        PlannedRound.objects.create(
            route=self.route,
            assigned_to=self.emp1,
            planned_start=now,
            planned_end=now + timedelta(hours=2),
        )
        PlannedRound.objects.create(
            route=self.route,
            assigned_to=self.emp2,
            planned_start=now + timedelta(hours=3),
            planned_end=now + timedelta(hours=5),
        )

        self.client.login(username='emp1_rt', password='pass')
        r = self.client.get('/ecopark/rounds/my/')
        self.assertEqual(r.status_code, 200)
        for round_obj in r.context['rounds']:
            self.assertEqual(round_obj.assigned_to, self.emp1)

    def test_unauthenticated_redirects(self):
        r = self.client.get('/ecopark/rounds/my/')
        self.assertIn(r.status_code, [302, 403])

    def test_substitute_gets_access(self):
        now = timezone.now()
        self.route.substitute_employee = self.emp2
        self.route.substitute_from = now - timedelta(hours=1)
        self.route.substitute_to = now + timedelta(hours=1)
        self.route.save()

        assignee = self.route.get_current_assignee()
        self.assertEqual(assignee, self.emp2)