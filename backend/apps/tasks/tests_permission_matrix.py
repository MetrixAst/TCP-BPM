from datetime import date, timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount, Employee, Department
from account.models_rbac import AppPermission, UserPermissionOverride
from addits.models import Comment
from hr.models import Company
from tasks.enums import TaskStatusEnum
from tasks.models import Task


class TaskPermissionMatrixTest(TestCase):
    """Отдельные права на просмотр всех, правку, удаление и переназначение задач."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        company = Company.objects.create(name='Matrix Co', bin_number='787878787878')
        self.dept = Department.objects.create(name='Офис', company=company)

        def user(name):
            account = UserAccount.objects.create_user(username=name, password='pass', role='staff', first_name=name)
            Employee.objects.create(user=account, department=self.dept, status='active')
            return account

        self.author = user('t_author')
        self.executor = user('t_executor')
        self.new_executor = user('t_new_exec')
        self.director = user('t_director')
        self.task = Task.objects.create(
            author=self.author, executor=self.executor, title='Подготовить отчёт',
            deadline=date.today() + timedelta(days=3), status=TaskStatusEnum.CREATED.value[0],
        )

    def _grant(self, user, code):
        UserPermissionOverride.objects.create(
            user=user, permission=AppPermission.objects.get(code=code), effect='ALLOW',
        )
        cache.clear()

    def test_view_all(self):
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(reverse('tasks:task', args=[self.task.pk])).status_code, 404)
        self._grant(self.director, 'tasks_view_all')
        self.assertEqual(self.client.get(reverse('tasks:task', args=[self.task.pk])).status_code, 200)

    def test_edit_any_keeps_author(self):
        self._grant(self.director, 'tasks_view_all')
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(reverse('tasks:edit', args=[self.task.pk])).status_code, 404)

        self._grant(self.director, 'tasks_edit_any')
        self.assertEqual(self.client.get(reverse('tasks:edit', args=[self.task.pk])).status_code, 200)
        self.assertTrue(self.task.can_edit(self.director))

    def test_delete_any(self):
        self._grant(self.director, 'tasks_view_all')
        self.assertFalse(self.task.can_delete(self.director))
        self._grant(self.director, 'tasks_delete')
        self.assertTrue(self.task.can_delete(self.director))

    def test_reassign_by_author(self):
        self.client.force_login(self.author)
        self.client.post(reverse('tasks:reassign', args=[self.task.pk]), {'executor': self.new_executor.pk})
        self.task.refresh_from_db()
        self.assertEqual(self.task.executor, self.new_executor)
        self.assertTrue(Comment.objects.filter(target_type='task', target_id=self.task.pk).exists())

    def test_reassign_forbidden_for_executor_without_permission(self):
        self.client.force_login(self.executor)
        response = self.client.post(reverse('tasks:reassign', args=[self.task.pk]), {'executor': self.new_executor.pk})
        self.assertEqual(response.status_code, 403)

        self._grant(self.executor, 'tasks_assign')
        self.client.post(reverse('tasks:reassign', args=[self.task.pk]), {'executor': self.new_executor.pk})
        self.task.refresh_from_db()
        self.assertEqual(self.task.executor, self.new_executor)

    def test_create_requires_edit_task(self):
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(reverse('tasks:edit', args=[0])).status_code, 200)
        UserPermissionOverride.objects.create(
            user=self.director, permission=AppPermission.objects.get(code='edit_task'), effect='DENY',
        )
        cache.clear()
        self.assertEqual(self.client.get(reverse('tasks:edit', args=[0])).status_code, 403)
