from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch
from rest_framework.test import APIClient

from account.models import UserAccount
from tasks.models import Task


def make_user(username, role='staff'):
    return UserAccount.objects.create_user(username=username, password='test1234', role=role)


def make_task(author, title='Test Task'):
    return Task.objects.create(
        author=author,
        title=title,
        deadline=timezone.now().date(),
        status='created',
    )


class BinAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_bin', role='administrator')
        self.staff = make_user('staff_bin', role='staff')
        self.author = make_user('author_bin')
        self.task = make_task(self.author)
        self.task.soft_delete(self.author, reason='тест корзины')

    def test_admin_sees_bin(self):
        self.client.force_authenticate(user=self.admin)
        r = self.client.get('/api/v1/tasks/bin/')
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.data['results']), 0)

    def test_staff_cannot_see_bin(self):
        self.client.force_authenticate(user=self.staff)
        r = self.client.get('/api/v1/tasks/bin/')
        self.assertEqual(r.status_code, 403)


class CleanupBinTaskTest(TestCase):

    def setUp(self):
        self.author = make_user('author_cleanup')
        self.task_old = make_task(self.author, title='Старая задача')
        self.task_new = make_task(self.author, title='Новая задача')

        self.task_old.soft_delete(self.author, reason='старое удаление')
        Task.objects.filter(pk=self.task_old.pk).update(
            deleted_at=timezone.now() - timedelta(days=31)
        )

        self.task_new.soft_delete(self.author, reason='новое удаление')

    def test_cleanup_removes_old_deletes_new(self):
        from tasks.tasks import cleanup_bin
        cleanup_bin(days=30)

        self.assertFalse(Task.objects.filter(pk=self.task_old.pk).exists())
        self.assertTrue(Task.objects.filter(pk=self.task_new.pk).exists())

    def test_cleanup_returns_count(self):
        from tasks.tasks import cleanup_bin
        result = cleanup_bin(days=30)
        self.assertIn('1', result)


class NotificationOnDeleteTest(TestCase):

    def setUp(self):
        self.author = make_user('author_notif')
        self.executor = make_user('executor_notif')
        self.task = make_task(self.author)
        self.task.executor = self.executor
        self.task.save()

    @patch('account.tasks.send_notifications_task.delay')
    def test_notification_sent_on_delete(self, mock_delay):
        from account.models import Notification
        count_before = Notification.objects.count()
        self.task.soft_delete(self.author, reason='тест уведомления')
        count_after = Notification.objects.count()
        self.assertGreater(count_after, count_before)