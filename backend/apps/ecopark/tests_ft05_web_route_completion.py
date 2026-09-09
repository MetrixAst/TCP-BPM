from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta

from account.models import UserAccount, Employee, Department
from hr.models import Company
from .models import (
    EcoObject, ChecklistTemplate, ChecklistItem, RoundPoint,
    Route, RoutePoint, PlannedRound,
)


def make_setup():
    company = Company.objects.create(name='FT05 Web Co', bin_number='777888999000')
    dept = Department.objects.create(name='FT05 Web Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_ft05w', password='pass', role='administrator')
    staff_user = UserAccount.objects.create_user(username='staff_ft05w', password='pass', role='staff')
    employee = Employee.objects.create(user=staff_user, department=dept, status='active')

    eco = EcoObject.objects.create(name='FT05 Web Eco')
    checklist = ChecklistTemplate.objects.create(name='FT05 Web Checklist', created_by=admin)
    item = ChecklistItem.objects.create(template=checklist, order=0, text='Пункт', requires_photo_on_fail=False)
    point1 = RoundPoint.objects.create(name='FT05 Web Точка 1', eco_object=eco, checklist=checklist, created_by=admin)
    point2 = RoundPoint.objects.create(name='FT05 Web Точка 2', eco_object=eco, checklist=checklist, created_by=admin)

    route = Route.objects.create(name='FT05 Web Маршрут', assigned_employee=staff_user, created_by=admin)
    RoutePoint.objects.create(route=route, point=point1, order=1)
    RoutePoint.objects.create(route=route, point=point2, order=2)

    now = timezone.now()
    planned = PlannedRound.objects.create(
        route=route, assigned_to=staff_user,
        planned_start=now - timedelta(minutes=5), planned_end=now + timedelta(hours=4),
    )

    return admin, staff_user, employee, point1, point2, item, planned


class WebRoundsScanCompletesPlannedRoundTest(TestCase):
    """rounds_scan (веб) должен закрывать PlannedRound так же, как это уже
    делает мобильный RoundPointAnswerView — иначе журнал план/факт никогда
    не покажет "Завершён" для обходов, пройденных через веб (FE-FT-05)."""

    def setUp(self):
        self.client = Client()
        self.admin, self.staff_user, self.employee, self.point1, self.point2, self.item, self.planned = make_setup()
        self.client.force_login(self.staff_user)

    def _scan(self, point):
        return self.client.post(f'/ecopark/rounds/scan/{point.uuid}/', {
            f'item_{self.item.pk}_passed': 'yes',
            f'item_{self.item.pk}_comment': '',
        })

    def test_single_point_route_marks_completed(self):
        # Второй маршрут из одной точки, чтобы не зависеть от точки 2.
        from .models import Route, RoutePoint
        single_route = Route.objects.create(name='FT05 Web Одна точка', assigned_employee=self.staff_user, created_by=self.admin)
        RoutePoint.objects.create(route=single_route, point=self.point1, order=1)
        now = timezone.now()
        single_planned = PlannedRound.objects.create(
            route=single_route, assigned_to=self.staff_user,
            planned_start=now - timedelta(minutes=5), planned_end=now + timedelta(hours=4),
        )

        r = self._scan(self.point1)
        self.assertEqual(r.status_code, 200)

        single_planned.refresh_from_db()
        self.assertEqual(single_planned.status, PlannedRound.STATUS_COMPLETED)
        self.assertIsNotNone(single_planned.completed_at)

    def test_multi_point_route_stays_pending_until_all_visited(self):
        r = self._scan(self.point1)
        self.assertEqual(r.status_code, 200)

        self.planned.refresh_from_db()
        self.assertEqual(self.planned.status, PlannedRound.STATUS_PENDING)

        r2 = self._scan(self.point2)
        self.assertEqual(r2.status_code, 200)

        self.planned.refresh_from_db()
        self.assertEqual(self.planned.status, PlannedRound.STATUS_COMPLETED)
        self.assertIsNotNone(self.planned.completed_at)

    def test_visit_outside_window_does_not_complete_round(self):
        from .models import Route, RoutePoint
        past_route = Route.objects.create(name='FT05 Web Прошлый', assigned_employee=self.staff_user, created_by=self.admin)
        RoutePoint.objects.create(route=past_route, point=self.point1, order=1)
        yesterday = timezone.now() - timedelta(days=1)
        past_planned = PlannedRound.objects.create(
            route=past_route, assigned_to=self.staff_user,
            planned_start=yesterday - timedelta(hours=2), planned_end=yesterday - timedelta(hours=1),
        )

        r = self._scan(self.point1)
        self.assertEqual(r.status_code, 200)

        past_planned.refresh_from_db()
        self.assertEqual(past_planned.status, PlannedRound.STATUS_PENDING)

    def test_other_employees_planned_round_untouched(self):
        other_user = UserAccount.objects.create_user(username='other_ft05w', password='pass', role='staff')
        Employee.objects.create(user=other_user, department=self.employee.department, status='active')
        from .models import Route, RoutePoint
        other_route = Route.objects.create(name='FT05 Web Чужой', assigned_employee=other_user, created_by=self.admin)
        RoutePoint.objects.create(route=other_route, point=self.point1, order=1)
        now = timezone.now()
        other_planned = PlannedRound.objects.create(
            route=other_route, assigned_to=other_user,
            planned_start=now - timedelta(minutes=5), planned_end=now + timedelta(hours=4),
        )

        self._scan(self.point1)

        other_planned.refresh_from_db()
        self.assertEqual(other_planned.status, PlannedRound.STATUS_PENDING)
