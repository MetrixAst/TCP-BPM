from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from account.models import Department, Employee, UserAccount
from ecopark.models import PlannedRound, Route
from hr.models import AttendanceRecord, Company
from mobile_api.tasks import refresh_review_demo
from tasks.models import Task
from tickets.models import ServiceRequest


class SeedReviewDemoTest(TestCase):

    def setUp(self):
        company = Company.objects.create(name='Demo Co', bin_number='111222333444')
        department = Department.objects.create(name='Эксплуатация', company=company)
        self.user = UserAccount.objects.create_user(
            username='appreview', password='pass', role='staff',
        )
        self.employee = Employee.objects.create(
            user=self.user, department=department, status='active',
        )

    def test_seeds_rounds_with_different_progress(self):
        call_command('seed_review_demo')

        today = timezone.now().date()
        rounds = list(
            PlannedRound.objects
            .filter(assigned_to=self.user, planned_start__date=today)
            .order_by('planned_start')
        )

        self.assertEqual(len(rounds), 3)
        self.assertEqual(
            [r.status for r in rounds],
            [
                PlannedRound.STATUS_COMPLETED,
                PlannedRound.STATUS_IN_PROGRESS,
                PlannedRound.STATUS_PENDING,
            ],
        )
        self.assertEqual([r.completed_points_count() for r in rounds], [5, 2, 0])
        self.assertEqual([r.total_points_count() for r in rounds], [5, 5, 5])

    def test_seeds_attendance_task_and_ticket_data(self):
        call_command('seed_review_demo')

        self.assertEqual(
            AttendanceRecord.objects.filter(employee=self.employee).count(), 1,
        )
        self.assertTrue(Task.objects.filter(executor=self.user).exists())
        self.assertTrue(ServiceRequest.objects.filter(author=self.user).exists())

    def test_route_and_points_have_no_demo_prefix(self):
        call_command('seed_review_demo')

        route = Route.objects.get(assigned_employee=self.user)
        self.assertNotIn('Демо', route.name)
        for rp in route.route_points.select_related('point'):
            self.assertNotIn('Демо', rp.point.name)

    def test_second_run_does_not_duplicate(self):
        """Команда идемпотентна: её гоняет celery-beat каждый день."""
        call_command('seed_review_demo')
        call_command('seed_review_demo')

        today = timezone.now().date()

        self.assertEqual(
            PlannedRound.objects.filter(
                assigned_to=self.user, planned_start__date=today,
            ).count(),
            3,
        )
        self.assertEqual(
            AttendanceRecord.objects.filter(employee=self.employee).count(), 1,
        )
        self.assertEqual(Task.objects.filter(executor=self.user).count(), 4)
        self.assertEqual(ServiceRequest.objects.filter(author=self.user).count(), 4)
        self.assertEqual(Route.objects.filter(assigned_employee=self.user).count(), 1)
        self.assertEqual(
            Route.objects.get(assigned_employee=self.user).route_points.count(), 5,
        )

    def test_missing_user_raises(self):
        with self.assertRaises(CommandError):
            call_command('seed_review_demo', username='no_such_user')


class RefreshReviewDemoTaskTest(TestCase):

    def test_missing_account_does_not_break_the_schedule(self):
        result = refresh_review_demo(username='no_such_user')

        self.assertIn('пропущено', result)
