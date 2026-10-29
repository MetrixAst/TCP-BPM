import io
from datetime import date, timedelta

import openpyxl
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import UserAccount, Employee, Department
from account.role_permissions import MenuItem
from hr.models import Company
from tasks.models import Task
from .models import DepartmentPlan, PlanItem, month_start


class PlansTest(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        company = Company.objects.create(name='Plans Co', bin_number='565656565656')
        self.cleaning = Department.objects.create(name='Клининг', company=company)
        self.security = Department.objects.create(name='СБ', company=company)

        def user(username, dept, role='staff', head=False):
            account = UserAccount.objects.create_user(
                username=username, password='pass', role=role, first_name=username,
            )
            Employee.objects.create(user=account, department=dept, status='active', head=head)
            return account

        self.head = user('cleaning_head', self.cleaning, head=True)
        self.worker = user('cleaner', self.cleaning)
        self.other_head = user('sb_head', self.security, head=True)
        self.owner = UserAccount.objects.create_user(username='owner_pl', password='pass', role='owner')
        self.month = month_start()

    def _create_plan(self, user=None, **extra):
        self.client.force_login(user or self.head)
        self.client.post(reverse('plans:create'), {
            'department': self.cleaning.pk, 'month': f'{self.month:%Y-%m}', **extra,
        })
        return DepartmentPlan.objects.get(department=self.cleaning, month=self.month)

    def _add_item(self, plan, deadline=None, title='Генуборка 2 этажа'):
        self.client.post(reverse('plans:item_create', args=[plan.pk]), {
            'title': title, 'responsible': self.worker.pk, 'status': 'planned',
            'deadline': (deadline or self.month + timedelta(days=20)).isoformat(),
        })
        return plan.items.get(title=title)

    def test_head_creates_plan_and_items(self):
        plan = self._create_plan()
        self.assertEqual(plan.author, self.head)
        item = self._add_item(plan)
        self.assertEqual(item.responsible, self.worker)
        self.assertEqual(plan.stats()['total'], 1)

    def test_head_cannot_plan_other_department(self):
        self.client.force_login(self.other_head)
        response = self.client.post(reverse('plans:create'), {
            'department': self.cleaning.pk, 'month': f'{self.month:%Y-%m}',
        })
        self.assertEqual(response.status_code, 403)

    def test_owner_sees_all_plans_and_missing_departments(self):
        self._create_plan()
        self.client.force_login(self.owner)
        response = self.client.get(reverse('plans:list'))
        self.assertEqual(len(response.context['rows']), 1)
        self.assertIn(self.security, response.context['missing'])
        self.assertEqual(response.context['creatable'], [])

    def test_other_head_cannot_open_foreign_plan(self):
        plan = self._create_plan()
        self.client.force_login(self.other_head)
        self.assertEqual(self.client.get(reverse('plans:detail', args=[plan.pk])).status_code, 403)

    def test_responsible_updates_only_status_and_result(self):
        plan = self._create_plan()
        item = self._add_item(plan)
        self.client.force_login(self.worker)
        self.client.post(reverse('plans:item_edit', args=[item.pk]), {
            'status': 'done', 'result': 'Сделано', 'title': 'Подмена', 'deadline': '2000-01-01',
        })
        item.refresh_from_db()
        self.assertEqual(item.status, 'done')
        self.assertIsNotNone(item.completed_at)
        self.assertEqual(item.title, 'Генуборка 2 этажа')

        self.assertEqual(self.client.post(reverse('plans:item_delete', args=[item.pk])).status_code, 403)

    def test_overdue_counted(self):
        plan = self._create_plan()
        self._add_item(plan, deadline=timezone.localdate() - timedelta(days=1), title='Просрочка')
        self.assertEqual(plan.stats()['overdue'], 1)

    def test_task_created_and_status_synced(self):
        plan = self._create_plan()
        item = self._add_item(plan)
        self.client.post(reverse('plans:item_create_task', args=[item.pk]))
        item.refresh_from_db()
        self.assertIsNotNone(item.task)
        self.assertEqual(item.task.executor, self.worker)
        self.assertEqual(item.status, PlanItem.STATUS_IN_PROGRESS)

        Task.objects.filter(pk=item.task_id).update(status='completed')
        self.client.get(reverse('plans:detail', args=[plan.pk]))
        item.refresh_from_db()
        self.assertEqual(item.status, PlanItem.STATUS_DONE)

    def test_carry_over_unfinished_items(self):
        prev_month = date(self.month.year - (self.month.month == 1), (self.month.month - 2) % 12 + 1, 1)
        previous = DepartmentPlan.objects.create(department=self.cleaning, month=prev_month, author=self.head)
        PlanItem.objects.create(plan=previous, title='Не успели', responsible=self.worker, deadline=prev_month)
        PlanItem.objects.create(plan=previous, title='Готово', responsible=self.worker, deadline=prev_month, status='done')

        plan = self._create_plan(carry_over='on')
        self.assertEqual(list(plan.items.values_list('title', flat=True)), ['Не успели'])
        self.assertEqual(plan.items.get().deadline, self.month)

    def test_excel_export(self):
        plan = self._create_plan()
        self._add_item(plan)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('plans:export'))
        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        self.assertEqual(wb['Пункты'].max_row, 2)

    def test_menu_item(self):
        def ids(items):
            return {i.id for i in items} | {s.id for i in items for s in (i.submenu or [])}

        self.assertIn('plans', ids(MenuItem.generate_menu(self.owner)))
        self.assertIn('plans', ids(MenuItem.generate_menu(self.worker)))
