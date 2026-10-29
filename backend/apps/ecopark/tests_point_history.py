from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount, Employee, Department
from account.models_rbac import AppPermission, UserPermissionOverride
from hr.models import Company
from .models import RoundPoint, ChecklistTemplate, ChecklistItem, RoundVisit, RoundVisitAnswer


class RoundPointHistoryTest(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        company = Company.objects.create(name='History Co', bin_number='111222333444')
        self.cleaning = Department.objects.create(name='Клининг', company=company)
        self.ops = Department.objects.create(name='Эксплуатация', company=company)
        admin = UserAccount.objects.create_user(username='admin_hist', password='pass', role='administrator')

        checklist = ChecklistTemplate.objects.create(name='Клининг', created_by=admin)
        self.item = ChecklistItem.objects.create(template=checklist, order=0, text='Пол чистый')
        self.cleaning_point = RoundPoint.objects.create(
            name='Комната клининга', checklist=checklist, responsible_department=self.cleaning,
            check_interval_hours=8, created_by=admin,
        )
        self.ops_point = RoundPoint.objects.create(
            name='Щитовая', checklist=checklist, responsible_department=self.ops, created_by=admin,
        )

        self.worker_user = UserAccount.objects.create_user(username='cleaner', password='pass', role='staff')
        self.worker = Employee.objects.create(user=self.worker_user, department=self.cleaning, status='active')
        self.head_user = UserAccount.objects.create_user(username='cleaning_head', password='pass', role='staff')
        Employee.objects.create(user=self.head_user, department=self.cleaning, status='active', head=True)
        self.owner = UserAccount.objects.create_user(username='owner_hist', password='pass', role='owner')

        visit = RoundVisit.objects.create(point=self.cleaning_point, employee=self.worker, comment='ok')
        RoundVisitAnswer.objects.create(visit=visit, item=self.item, passed=False, comment='лужа')
        RoundVisit.objects.create(point=self.ops_point, employee=self.worker)

    def _history(self, point):
        return reverse('ecopark:round_point_history', args=[point.pk])

    def test_owner_sees_history_of_any_point(self):
        self.client.force_login(self.owner)
        response = self.client.get(self._history(self.ops_point))
        self.assertEqual(response.status_code, 200)

    def test_history_shows_visits_and_failed_items(self):
        self.client.force_login(self.owner)
        response = self.client.get(self._history(self.cleaning_point))
        self.assertContains(response, 'лужа')
        self.assertEqual(response.context['stats']['total'], 1)
        self.assertEqual(response.context['stats']['planned_interval_hours'], 8)

    def test_head_limited_to_own_department_points(self):
        self.client.force_login(self.head_user)
        self.assertEqual(self.client.get(self._history(self.cleaning_point)).status_code, 200)
        self.assertEqual(self.client.get(self._history(self.ops_point)).status_code, 403)

        journal = self.client.get(reverse('ecopark:rounds_journal'))
        points = {v.point_id for v in journal.context['visits']}
        self.assertEqual(points, {self.cleaning_point.pk})

    def test_regular_employee_has_no_history(self):
        self.client.force_login(self.worker_user)
        self.assertEqual(self.client.get(self._history(self.cleaning_point)).status_code, 403)

    def test_scan_by_monitor_not_assigned_redirects_to_history(self):
        self.client.force_login(self.owner)
        Employee.objects.create(user=self.owner, department=self.ops, status='active')
        response = self.client.get(reverse('ecopark:rounds_scan', args=[self.cleaning_point.uuid]))
        self.assertRedirects(response, self._history(self.cleaning_point))

    def test_scan_by_assigned_worker_shows_checklist(self):
        self.client.force_login(self.worker_user)
        response = self.client.get(reverse('ecopark:rounds_scan', args=[self.cleaning_point.uuid]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_view_history'])

    def test_individual_rounds_monitor_grant(self):
        UserPermissionOverride.objects.create(
            user=self.worker_user,
            permission=AppPermission.objects.get(code='rounds_monitor'),
            effect='ALLOW',
        )
        self.client.force_login(self.worker_user)
        self.assertEqual(self.client.get(self._history(self.ops_point)).status_code, 200)
