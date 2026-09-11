from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta

from account.models import UserAccount, Employee, Department
from account.role_permissions import MenuItem
from hr.models import Company
from ecopark.models import (
    EcoObject, RoundPoint, ChecklistTemplate,
    Route, RoutePoint, RouteSchedule, PlannedRound,
)


def make_setup():
    company = Company.objects.create(name='Routes FE Co', bin_number='111222333999')
    dept = Department.objects.create(name='Routes FE Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_rtfe', password='pass', role='administrator')
    head_user = UserAccount.objects.create_user(username='head_rtfe', password='pass', role='staff')
    staff_user = UserAccount.objects.create_user(username='staff_rtfe', password='pass', role='staff')
    Employee.objects.create(user=head_user, department=dept, status='active', head=True)
    Employee.objects.create(user=staff_user, department=dept, status='active')

    eco_obj = EcoObject.objects.create(name='Корпус Б')
    template = ChecklistTemplate.objects.create(name='Шаблон FE', created_by=admin)
    point1 = RoundPoint.objects.create(name='FE Точка 1', eco_object=eco_obj, checklist=template, created_by=admin)
    point2 = RoundPoint.objects.create(name='FE Точка 2', eco_object=eco_obj, checklist=template, created_by=admin)

    route = Route.objects.create(name='FE Маршрут', assigned_employee=staff_user, created_by=admin)
    RoutePoint.objects.create(route=route, point=point1, order=1)
    RoutePoint.objects.create(route=route, point=point2, order=2)

    return admin, head_user, staff_user, route, point1, point2, dept


class RoutesAdminAccessTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, self.head_user, self.staff_user, self.route, self.point1, self.point2, self.dept = make_setup()

    def test_admin_can_open_routes_list(self):
        self.client.login(username='admin_rtfe', password='pass')
        r = self.client.get('/ecopark/rounds/routes/')
        self.assertEqual(r.status_code, 200)

    def test_staff_forbidden_from_routes_list(self):
        self.client.login(username='staff_rtfe', password='pass')
        r = self.client.get('/ecopark/rounds/routes/')
        self.assertEqual(r.status_code, 403)

    def test_department_head_without_ecopark_forbidden_from_routes_config(self):
        # Голова отдела видит журналы (ROUNDS_MONITOR), но не имеет права
        # настраивать маршруты — это остаётся действием полного ECOPARK-админа.
        self.client.login(username='head_rtfe', password='pass')
        r = self.client.get('/ecopark/rounds/routes/')
        self.assertEqual(r.status_code, 403)

    def test_anonymous_redirected_from_routes_list(self):
        r = self.client.get('/ecopark/rounds/routes/')
        self.assertIn(r.status_code, (302, 403))


class PlannedRoundsJournalAccessTest(TestCase):
    """planned_rounds_journal должен быть доступен так же широко, как
    rounds_journal/defects_list — полным ECOPARK-админам и руководителям
    отделов (ROUNDS_MONITOR), а не только полным админам."""

    def setUp(self):
        self.client = Client()
        self.admin, self.head_user, self.staff_user, self.route, self.point1, self.point2, self.dept = make_setup()

    def test_admin_can_open_journal(self):
        self.client.login(username='admin_rtfe', password='pass')
        r = self.client.get('/ecopark/rounds/planned/')
        self.assertEqual(r.status_code, 200)

    def test_department_head_can_open_journal(self):
        self.client.login(username='head_rtfe', password='pass')
        r = self.client.get('/ecopark/rounds/planned/')
        self.assertEqual(r.status_code, 200)

    def test_plain_staff_forbidden_from_journal(self):
        self.client.login(username='staff_rtfe', password='pass')
        r = self.client.get('/ecopark/rounds/planned/')
        self.assertEqual(r.status_code, 403)

    def test_anonymous_redirected_from_journal(self):
        r = self.client.get('/ecopark/rounds/planned/')
        self.assertIn(r.status_code, (302, 403))


class RouteCreateEditTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, self.head_user, self.staff_user, self.route, self.point1, self.point2, self.dept = make_setup()
        self.client.login(username='admin_rtfe', password='pass')

    def test_create_route_with_points_and_schedule(self):
        r = self.client.post('/ecopark/rounds/routes/create/', {
            'name': 'Новый маршрут',
            'points': [str(self.point2.pk), str(self.point1.pk)],
            'frequency': 'weekly',
            'interval_hours': '48',
            'window_hours': '3',
        })
        self.assertEqual(r.status_code, 302)
        route = Route.objects.get(name='Новый маршрут')
        ordered = list(route.route_points.order_by('order').values_list('point_id', flat=True))
        self.assertEqual(ordered, [self.point2.pk, self.point1.pk])
        schedule = route.schedules.first()
        self.assertIsNotNone(schedule)
        self.assertEqual(schedule.frequency, 'weekly')
        self.assertEqual(schedule.interval_hours, 48)

    def test_create_route_with_substitute_period_naive_datetime_local(self):
        r = self.client.post('/ecopark/rounds/routes/create/', {
            'name': 'Маршрут с заместителем',
            'substitute_employee': str(self.staff_user.pk),
            'substitute_from': '2026-09-10T09:00',
            'substitute_to': '2026-09-12T18:00',
        })
        self.assertEqual(r.status_code, 302)
        route = Route.objects.get(name='Маршрут с заместителем')
        self.assertIsNotNone(route.substitute_from)
        self.assertTrue(timezone.is_aware(route.substitute_from))

    def test_create_route_requires_name(self):
        r = self.client.post('/ecopark/rounds/routes/create/', {'name': ''})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'обязательно')

    def test_edit_route_updates_points_and_schedule(self):
        RouteSchedule.objects.create(route=self.route, frequency='daily', interval_hours=24, window_hours=2)
        r = self.client.post(f'/ecopark/rounds/routes/{self.route.pk}/edit/', {
            'name': self.route.name,
            'points': [str(self.point1.pk)],
            'frequency': 'custom',
            'interval_hours': '12',
            'window_hours': '1',
            'is_active': 'on',
        })
        self.assertEqual(r.status_code, 302)
        self.route.refresh_from_db()
        remaining = list(self.route.route_points.values_list('point_id', flat=True))
        self.assertEqual(remaining, [self.point1.pk])
        schedule = self.route.schedules.first()
        self.assertEqual(schedule.frequency, 'custom')
        self.assertEqual(schedule.interval_hours, 12)

    def test_delete_route_deactivates_not_deletes(self):
        r = self.client.post(f'/ecopark/rounds/routes/{self.route.pk}/delete/')
        self.assertEqual(r.status_code, 302)
        self.route.refresh_from_db()
        self.assertFalse(self.route.is_active)
        self.assertTrue(Route.objects.filter(pk=self.route.pk).exists())


class PlannedRoundCreateTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, self.head_user, self.staff_user, self.route, self.point1, self.point2, self.dept = make_setup()
        self.client.login(username='admin_rtfe', password='pass')

    def test_create_planned_round_naive_datetime_local(self):
        r = self.client.post('/ecopark/rounds/planned/create/', {
            'route': str(self.route.pk),
            'planned_start': '2026-09-15T08:00',
            'window_hours': '2',
        })
        self.assertEqual(r.status_code, 302)
        planned = PlannedRound.objects.get(route=self.route)
        self.assertTrue(timezone.is_aware(planned.planned_start))
        self.assertEqual(planned.assigned_to, self.staff_user)

    def test_create_planned_round_missing_start_shows_error_not_500(self):
        r = self.client.post('/ecopark/rounds/planned/create/', {
            'route': str(self.route.pk),
            'planned_start': '',
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Укажите маршрут')

    def test_create_planned_round_missing_route_shows_error_not_404(self):
        r = self.client.post('/ecopark/rounds/planned/create/', {
            'route': '',
            'planned_start': '2026-09-15T08:00',
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Укажите маршрут')


class MyPlannedRoundsProgressTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, self.head_user, self.staff_user, self.route, self.point1, self.point2, self.dept = make_setup()

    def test_progress_reflects_completed_visits(self):
        from ecopark.models import RoundVisit
        now = timezone.now()
        planned = PlannedRound.objects.create(
            route=self.route,
            assigned_to=self.staff_user,
            planned_start=now - timedelta(minutes=5),
            planned_end=now + timedelta(hours=2),
        )
        RoundVisit.objects.create(
            point=self.point1,
            employee=self.staff_user.employee_info,
            created_at=now,
        )
        self.client.login(username='staff_rtfe', password='pass')
        r = self.client.get('/ecopark/rounds/my/')
        self.assertEqual(r.status_code, 200)
        result = r.context['rounds'][0]
        self.assertEqual(result.progress_completed, 1)
        self.assertEqual(result.progress_total, 2)
        self.assertEqual(result.next_point, self.point2)

    def test_no_next_point_when_all_visited(self):
        from ecopark.models import RoundVisit
        now = timezone.now()
        planned = PlannedRound.objects.create(
            route=self.route,
            assigned_to=self.staff_user,
            planned_start=now - timedelta(minutes=5),
            planned_end=now + timedelta(hours=2),
        )
        for p in (self.point1, self.point2):
            RoundVisit.objects.create(
                point=p,
                employee=self.staff_user.employee_info,
                created_at=now,
            )
        self.client.login(username='staff_rtfe', password='pass')
        r = self.client.get('/ecopark/rounds/my/')
        result = r.context['rounds'][0]
        self.assertIsNone(result.next_point)
        self.assertEqual(result.progress_completed, 2)


class MyRoundsVisibilityTest(TestCase):

    def setUp(self):
        self.client = Client()
        (
            self.admin,
            self.head_user,
            self.staff_user,
            self.route,
            self.point1,
            self.point2,
            self.dept,
        ) = make_setup()
        self.unassigned_user = UserAccount.objects.create_user(
            username='unassigned_rtfe',
            password='pass',
            role='staff',
        )
        Employee.objects.create(
            user=self.unassigned_user,
            department=self.dept,
            status='active',
        )

    @staticmethod
    def _menu_ids(user):
        return {item.id for item in MenuItem.generate_menu(user)}

    def test_unassigned_employee_does_not_see_rounds_and_cannot_open_page(self):
        self.assertNotIn('my_planned_rounds', self._menu_ids(self.unassigned_user))
        self.client.login(username='unassigned_rtfe', password='pass')
        response = self.client.get('/ecopark/rounds/my/')
        self.assertEqual(response.status_code, 403)

    def test_directly_assigned_employee_sees_rounds_and_can_open_page(self):
        self.assertIn('my_planned_rounds', self._menu_ids(self.staff_user))
        self.client.login(username='staff_rtfe', password='pass')
        response = self.client.get('/ecopark/rounds/my/')
        self.assertEqual(response.status_code, 200)

    def test_department_assignment_grants_rounds_access(self):
        Route.objects.create(
            name='Маршрут отдела',
            assigned_department=self.dept,
            created_by=self.admin,
        )
        self.assertIn('my_planned_rounds', self._menu_ids(self.unassigned_user))

    def test_existing_planned_round_keeps_history_access(self):
        self.route.assigned_employee = None
        self.route.is_active = False
        self.route.save(update_fields=['assigned_employee', 'is_active'])
        now = timezone.now()
        PlannedRound.objects.create(
            route=self.route,
            assigned_to=self.unassigned_user,
            planned_start=now - timedelta(days=2),
            planned_end=now - timedelta(days=2) + timedelta(hours=2),
            status=PlannedRound.STATUS_COMPLETED,
        )
        self.assertIn('my_planned_rounds', self._menu_ids(self.unassigned_user))
