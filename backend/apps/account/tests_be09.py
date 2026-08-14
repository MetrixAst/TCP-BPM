from django.test import TestCase
from rest_framework.test import APIClient
from django.utils import timezone

from account.models import UserAccount, Notification, NotificationUser


def make_user(username, role='staff'):
    return UserAccount.objects.create_user(username=username, password='pass', role=role)


def make_notification(title='Test', users=None):
    n = Notification.objects.create(
        title=title,
        text='Test text',
        target_id=1,
        target_type='task',
    )
    if users:
        n.users.add(*users)
    return n


class NotificationDismissTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user1 = make_user('user1_be09')
        self.user2 = make_user('user2_be09')
        self.client.force_authenticate(user=self.user1)

    def test_dismiss_one(self):
        n = make_notification(users=[self.user1, self.user2])
        r = self.client.delete(f'/api/v1/notifications/{n.pk}/dismiss/')
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Notification.objects.filter(pk=n.pk, users=self.user1).exists())
        self.assertTrue(Notification.objects.filter(pk=n.pk, users=self.user2).exists())

    def test_dismiss_all(self):
        make_notification('n1', users=[self.user1])
        make_notification('n2', users=[self.user1])
        make_notification('n3', users=[self.user1, self.user2])
        r = self.client.delete('/api/v1/notifications/dismiss-all/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Notification.objects.filter(users=self.user1).count(), 0)
        self.assertEqual(Notification.objects.filter(users=self.user2).count(), 1)

    def test_dismiss_read(self):
        n1 = make_notification('read1', users=[self.user1])
        n2 = make_notification('unread1', users=[self.user1])
        NotificationUser.objects.update_or_create(
            notification=n1, user=self.user1,
            defaults={'is_read': True, 'read_at': timezone.now()}
        )
        r = self.client.delete('/api/v1/notifications/dismiss-read/')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Notification.objects.filter(pk=n1.pk, users=self.user1).exists())
        self.assertTrue(Notification.objects.filter(pk=n2.pk, users=self.user1).exists())

    def test_cannot_dismiss_others_notification(self):
        n = make_notification(users=[self.user2])
        r = self.client.delete(f'/api/v1/notifications/{n.pk}/dismiss/')
        self.assertEqual(r.status_code, 404)

    def test_mark_read(self):
        n = make_notification(users=[self.user1])
        r = self.client.post(f'/api/v1/notifications/{n.pk}/mark-read/')
        self.assertEqual(r.status_code, 200)
        nu = NotificationUser.objects.get(notification=n, user=self.user1)
        self.assertTrue(nu.is_read)
        self.assertIsNotNone(nu.read_at)

    def test_related_objects_not_affected(self):
        from tasks.models import Task
        admin = make_user('admin_be09', 'administrator')
        task = Task.objects.create(
            author=admin,
            title='Test task BE09',
            deadline=timezone.now().date(),
            status='created',
        )
        n = make_notification(users=[self.user1])
        self.client.delete(f'/api/v1/notifications/{n.pk}/dismiss/')
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())