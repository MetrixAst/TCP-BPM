from datetime import date, timedelta
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import UserAccount
from account.role_permissions import RoleEnums
from .models import Task
from .enums import TaskStatusEnum


@patch('account.models.send_notifications_task.delay')
class TaskAPITestCase(APITestCase):
    def setUp(self):
        self.author = UserAccount.objects.create_user(
            username='task_author',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        self.executor = UserAccount.objects.create_user(
            username='task_executor',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        self.guest = UserAccount.objects.create_user(
            username='task_guest',
            password='pass',
            role=RoleEnums.GUEST.value,
        )
        self.task = Task.objects.create(
            author=self.author,
            executor=self.executor,
            title='API Task',
            text='Body',
            deadline=date.today() + timedelta(days=7),
            status=TaskStatusEnum.CREATED.value[0],
        )
        self.list_url = reverse('task-list')
        self.detail_url = reverse('task-detail', kwargs={'pk': self.task.pk})

    def test_list_unauthenticated_401(self, _mock_delay):
        response = self.client.get(self.list_url)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_list_forbidden_without_tasks_permission(self, _mock_delay):
        self.client.force_authenticate(user=self.guest)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_and_retrieve_as_participant(self, _mock_delay):
        self.client.force_authenticate(user=self.author)
        list_response = self.client.get(self.list_url)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(list_response.data['count'], 1)

        detail_response = self.client.get(self.detail_url)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data['title'], 'API Task')

    def test_create_task(self, _mock_delay):
        self.client.force_authenticate(user=self.author)
        payload = {
            'title': 'New via API',
            'text': 'Desc',
            'deadline': (date.today() + timedelta(days=3)).isoformat(),
            'executor_id': self.executor.id,
        }
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Task.objects.filter(title='New via API').count(), 1)

    def test_transition_accept(self, _mock_delay):
        self.client.force_authenticate(user=self.executor)
        url = reverse('task-transition', kwargs={'pk': self.task.pk})
        response = self.client.post(url, {'action': 'accept'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatusEnum.ACCEPTED.value[0])

    def test_transition_forbidden_for_wrong_user(self, _mock_delay):
        self.client.force_authenticate(user=self.guest)
        url = reverse('task-transition', kwargs={'pk': self.task.pk})
        response = self.client.post(url, {'action': 'accept'}, format='json')
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
