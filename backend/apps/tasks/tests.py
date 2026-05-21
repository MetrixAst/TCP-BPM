from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount
from account.role_permissions import RoleEnums
from .models import Task
from .enums import TaskStatusEnum


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
