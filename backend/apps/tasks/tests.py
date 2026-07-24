from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount
from account.role_permissions import RoleEnums
from .models import Task
from .enums import TaskStatusEnum
from .serializers import TaskSerializer
from rest_framework.test import APIClient
from rest_framework import status

from mobile_api.models import IdempotencyKey

class TaskWorkflowTestCase(TestCase):
    def setUp(self):
        self.author = UserAccount.objects.create_user(
            username='wf_author',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        self.executor = UserAccount.objects.create_user(
            username='wf_executor',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        self.task = Task.objects.create(
            author=self.author,
            executor=self.executor,
            title='Workflow task',
            deadline=date.today() + timedelta(days=5),
            status=TaskStatusEnum.CREATED.value[0],
        )

    @patch('account.models.send_notifications_task.delay')
    def test_executor_accept_transition(self, _mock_delay):
        self.task.set_action(
            type('R', (), {'user': self.executor})(),
            'accept',
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatusEnum.ACCEPTED.value[0])

    @patch('account.models.send_notifications_task.delay')
    def test_executor_complete_transition(self, _mock_delay):
        self.task.status = TaskStatusEnum.ACCEPTED.value[0]
        self.task.save(update_fields=['status'])
        self.task.set_action(
            type('R', (), {'user': self.executor})(),
            'complete',
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatusEnum.COMPLETED.value[0])

    @patch('account.models.send_notifications_task.delay')
    def test_author_reopen_rejected(self, _mock_delay):
        self.task.status = TaskStatusEnum.REJECTED.value[0]
        self.task.save(update_fields=['status'])
        self.task.set_action(
            type('R', (), {'user': self.author})(),
            'reopen',
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatusEnum.CREATED.value[0])

    @patch('account.models.send_notifications_task.delay')
    def test_unauthorized_transition_raises(self, _mock_delay):
        outsider = UserAccount.objects.create_user(
            username='wf_outsider',
            password='pass',
            role=RoleEnums.GUEST.value,
        )
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            self.task.set_action(
                type('R', (), {'user': outsider})(),
                'accept',
            )

    def test_available_queryset_scopes_participant(self):
        qs = Task.get_available_queryset(
            type('R', (), {'user': self.executor})(),
        )
        self.assertIn(self.task, qs)
        outsider = UserAccount.objects.create_user(
            username='wf_outsider2',
            password='pass',
            role=RoleEnums.GUEST.value,
        )
        qs_out = Task.get_available_queryset(
            type('R', (), {'user': outsider})(),
        )
        self.assertNotIn(self.task, qs_out)

class TaskSerializerMobileFieldsTestCase(TestCase):
    def setUp(self):
        self.author = UserAccount.objects.create_user(
            username='ser_author',
            password='pass',
            role=RoleEnums.STAFF.value,
        )

    def test_status_display_and_color_present(self):
        task = Task.objects.create(
            author=self.author,
            title='Serializer task',
            deadline=date.today() + timedelta(days=3),
            status=TaskStatusEnum.CREATED.value[0],
        )

        data = TaskSerializer(task).data

        self.assertEqual(data['status_display'], 'Создана')
        self.assertEqual(data['status_color'], 'neutral')

    def test_status_color_reflects_rejected_state(self):
        task = Task.objects.create(
            author=self.author,
            title='Rejected task',
            deadline=date.today() + timedelta(days=3),
            status=TaskStatusEnum.REJECTED.value[0],
        )

        data = TaskSerializer(task).data

        self.assertEqual(data['status_color'], 'danger')

    def test_priority_display_present(self):
        task = Task.objects.create(
            author=self.author,
            title='Priority task',
            deadline=date.today() + timedelta(days=3),
            status=TaskStatusEnum.CREATED.value[0],
            priority='critical',
        )

        data = TaskSerializer(task).data

        self.assertEqual(data['priority_display'], 'Критический')

    def test_existing_status_display_still_returns_plain_title(self):
        # Регрессионный тест: убеждаемся, что старое поле status_display
        # не сломалось при добавлении status_color рядом с ним.
        task = Task.objects.create(
            author=self.author,
            title='Regression task',
            deadline=date.today() + timedelta(days=3),
            status=TaskStatusEnum.COMPLETED.value[0],
        )

        data = TaskSerializer(task).data

        self.assertEqual(data['status_display'], 'Завершена')
        self.assertIsInstance(data['status_display'], str)

class TaskTransitionIdempotencyTestCase(TestCase):
    def setUp(self):
        self.author = UserAccount.objects.create_user(
            username='idem_task_author',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        self.executor = UserAccount.objects.create_user(
            username='idem_task_executor',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        self.task = Task.objects.create(
            author=self.author,
            executor=self.executor,
            title='Idempotency transition task',
            deadline=date.today() + timedelta(days=5),
            status=TaskStatusEnum.CREATED.value[0],
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.executor)
        self.transition_url = reverse('task-transition', args=[self.task.id])

    @patch('account.models.send_notifications_task.delay')
    def test_repeated_transition_with_same_key_applies_once(self, _mock_delay):
        idempotency_key = 'test-key-transition-001'

        response1 = self.client.post(
            self.transition_url,
            {'action': 'accept'},
            format='json',
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(response1.data['status'], TaskStatusEnum.ACCEPTED.value[0])

        response2 = self.client.post(
            self.transition_url,
            {'action': 'accept'},
            format='json',
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data, response1.data)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatusEnum.ACCEPTED.value[0])

    @patch('account.models.send_notifications_task.delay')
    def test_without_key_repeated_transition_processes_normally(self, _mock_delay):
        response1 = self.client.post(
            self.transition_url, {'action': 'accept'}, format='json',
        )
        self.assertEqual(response1.status_code, status.HTTP_200_OK)

    def test_idempotency_key_recorded_with_correct_endpoint(self):
        with patch('account.models.send_notifications_task.delay'):
            self.client.post(
                self.transition_url,
                {'action': 'accept'},
                format='json',
                HTTP_IDEMPOTENCY_KEY='test-key-scope-task',
            )

        stored = IdempotencyKey.objects.filter(key='test-key-scope-task').first()
        self.assertIsNotNone(stored)
        self.assertEqual(stored.endpoint, 'task-transition')