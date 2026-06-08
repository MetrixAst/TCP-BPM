import json
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse

from account.models import UserAccount
from account.role_permissions import RoleEnums
from tasks.models import Task, TaskChecklist, TaskLineItem
from tasks.enums import TaskStatusEnum


class TaskWorkflowTestCase(TestCase):
    def setUp(self):
        self.author = UserAccount.objects.create_user(
            username='wf_author', password='pass', role=RoleEnums.STAFF.value,
        )
        self.executor = UserAccount.objects.create_user(
            username='wf_executor', password='pass', role=RoleEnums.STAFF.value,
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
        self.task.set_action(type('R', (), {'user': self.executor})(), 'accept')
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatusEnum.ACCEPTED.value[0])

    @patch('account.models.send_notifications_task.delay')
    def test_executor_complete_transition(self, _mock_delay):
        self.task.status = TaskStatusEnum.ACCEPTED.value[0]
        self.task.save(update_fields=['status'])
        self.task.set_action(type('R', (), {'user': self.executor})(), 'complete')
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatusEnum.COMPLETED.value[0])

    @patch('account.models.send_notifications_task.delay')
    def test_author_reopen_rejected(self, _mock_delay):
        self.task.status = TaskStatusEnum.REJECTED.value[0]
        self.task.save(update_fields=['status'])
        self.task.set_action(type('R', (), {'user': self.author})(), 'reopen')
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatusEnum.CREATED.value[0])

    @patch('account.models.send_notifications_task.delay')
    def test_unauthorized_transition_raises(self, _mock_delay):
        outsider = UserAccount.objects.create_user(
            username='wf_outsider', password='pass', role=RoleEnums.GUEST.value,
        )
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            self.task.set_action(type('R', (), {'user': outsider})(), 'accept')

    def test_available_queryset_scopes_participant(self):
        qs = Task.get_available_queryset(type('R', (), {'user': self.executor})())
        self.assertIn(self.task, qs)
        outsider = UserAccount.objects.create_user(
            username='wf_outsider2', password='pass', role=RoleEnums.GUEST.value,
        )
        qs_out = Task.get_available_queryset(type('R', (), {'user': outsider})())
        self.assertNotIn(self.task, qs_out)


class KanbanBoardTest(TestCase):

    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            username='admin_fix08', password='pass', role=RoleEnums.ADMINISTRATOR.value
        )
        self.executor = UserAccount.objects.create_user(
            username='executor_fix08', password='pass', role=RoleEnums.STAFF.value
        )
        self.task = Task.objects.create(
            title='Test Task',
            author=self.admin,
            executor=self.executor,
            status=TaskStatusEnum.CREATED.value[0],
            deadline=date.today(),
            priority='medium',
            task_type='assignment',
        )
        self.client = Client()

    def test_kanban_board_returns_json(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('tasks:kanban_board'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('board', response.json())

    def test_kanban_board_groups_by_status(self):
        self.client.force_login(self.admin)
        data = self.client.get(reverse('tasks:kanban_board')).json()
        statuses = [col['status'] for col in data['board']]
        self.assertIn(TaskStatusEnum.CREATED.value[0], statuses)

    def test_kanban_patch_status_accept(self):
        self.client.force_login(self.executor)
        response = self.client.patch(
            reverse('tasks:kanban_patch_status', args=[self.task.pk]),
            data=json.dumps({'action': 'accept'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatusEnum.ACCEPTED.value[0])

    def test_kanban_patch_wrong_role_forbidden(self):
        self.client.force_login(self.admin)
        response = self.client.patch(
            reverse('tasks:kanban_patch_status', args=[self.task.pk]),
            data=json.dumps({'action': 'accept'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_kanban_anonymous_redirected(self):
        response = self.client.get(reverse('tasks:kanban_board'))
        self.assertNotEqual(response.status_code, 200)

    def test_kanban_board_sort_by_deadline(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('tasks:kanban_board') + '?sort=deadline')
        self.assertEqual(response.status_code, 200)
        self.assertIn('board', response.json())

    def test_kanban_board_pagination(self):
        self.client.force_login(self.admin)
        data = self.client.get(reverse('tasks:kanban_board') + '?limit=1&offset=0').json()
        for col in data['board']:
            self.assertIn('has_more', col)
            self.assertLessEqual(len(col['tasks']), 1)


class TaskWorkflowTest(TestCase):

    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            username='admin_fix09', password='pass', role=RoleEnums.ADMINISTRATOR.value
        )
        self.executor = UserAccount.objects.create_user(
            username='executor_fix09', password='pass', role=RoleEnums.STAFF.value
        )
        self.task = Task.objects.create(
            title='Test Task Fix09',
            author=self.admin,
            executor=self.executor,
            status=TaskStatusEnum.CREATED.value[0],
            deadline=date.today(),
            priority='medium',
            task_type='assignment',
        )
        self.client = Client()

    def test_checklist_create(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('tasks:checklist_create', args=[self.task.pk]),
            data=json.dumps({'text': 'Test item'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(TaskChecklist.objects.filter(task=self.task, text='Test item').exists())

    def test_checklist_update(self):
        item = TaskChecklist.objects.create(task=self.task, text='Item 1', created_by=self.admin)
        self.client.force_login(self.admin)
        response = self.client.patch(
            reverse('tasks:checklist_update', args=[self.task.pk, item.pk]),
            data=json.dumps({'is_done': True}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.is_done)

    def test_checklist_delete(self):
        item = TaskChecklist.objects.create(task=self.task, text='Item to delete', created_by=self.admin)
        self.client.force_login(self.admin)
        response = self.client.delete(
            reverse('tasks:checklist_delete', args=[self.task.pk, item.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TaskChecklist.objects.filter(pk=item.pk).exists())

    def test_line_item_create(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('tasks:line_item_create', args=[self.task.pk]),
            data=json.dumps({'name': 'Product 1', 'quantity': 2, 'price': 100}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(TaskLineItem.objects.filter(task=self.task, name='Product 1').exists())

    def test_line_item_delete(self):
        item = TaskLineItem.objects.create(task=self.task, name='Product to delete')
        self.client.force_login(self.admin)
        response = self.client.delete(
            reverse('tasks:line_item_delete', args=[self.task.pk, item.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TaskLineItem.objects.filter(pk=item.pk).exists())

    def test_task_counterparty_field_exists(self):
        self.assertIsNone(self.task.counterparty)

    def test_task_history_text_field(self):
        from tasks.models import TaskHistory
        h = TaskHistory.objects.create(
            task=self.task,
            user=self.admin,
            status=TaskStatusEnum.CREATED.value[0],
            text='Test comment',
        )
        self.assertEqual(h.text, 'Test comment')