import json
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import UserAccount
from account.role_permissions import RoleEnums
from tasks.models import Task
from tasks.enums import TaskStatusEnum


class TaskKanbanTest(TestCase):
    def setUp(self):
        self.author = UserAccount.objects.create_user(
            username='author',
            email='author@test.kz',
            password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.executor = UserAccount.objects.create_user(
            username='executor',
            email='exec@test.kz',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        self.task = Task.objects.create(
            author=self.author,
            executor=self.executor,
            title='Kanban task',
            deadline=date.today() + timedelta(days=3),
            status=TaskStatusEnum.CREATED.value[0],
        )

    def test_kanban_api_returns_columns(self):
        self.client.login(username=self.author.username, password='pass')
        response = self.client.get(reverse('tasks:kanban_api'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('columns', data)
        statuses = [c['status'] for c in data['columns']]
        self.assertIn('created', statuses)

    @patch('account.tasks.send_notifications_task.delay')
    def test_kanban_status_patch_accept(self, _mock_delay):
        self.client.login(username=self.executor.username, password='pass')
        url = reverse('tasks:kanban_status', args=[self.task.pk])
        response = self.client.patch(
            url,
            data=json.dumps({'status': TaskStatusEnum.ACCEPTED.value[0]}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatusEnum.ACCEPTED.value[0])
