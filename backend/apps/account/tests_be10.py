from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from account.models import UserAccount, Notification


def make_user(username):
    return UserAccount.objects.create_user(username=username, password='pass', role='staff')


def make_notification(title='Test', days_ago=0):
    n = Notification.objects.create(
        title=title,
        text='Test text',
        target_id=1,
        target_type='task',
    )
    if days_ago > 0:
        Notification.objects.filter(pk=n.pk).update(
            created_date=timezone.now() - timedelta(days=days_ago)
        )
    return n


class NotificationCleanupTest(TestCase):

    def test_cleanup_removes_old_notifications(self):
        old = make_notification('old', days_ago=61)
        new = make_notification('new', days_ago=10)

        from account.tasks import cleanup_notifications
        result = cleanup_notifications(days=60)

        self.assertFalse(Notification.objects.filter(pk=old.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=new.pk).exists())
        self.assertIn('1', result)

    def test_cleanup_default_60_days(self):
        old = make_notification('old_default', days_ago=61)
        new = make_notification('new_default', days_ago=59)

        from account.tasks import cleanup_notifications
        cleanup_notifications()  # default=60

        self.assertFalse(Notification.objects.filter(pk=old.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=new.pk).exists())

    def test_cleanup_returns_count(self):
        make_notification('n1', days_ago=70)
        make_notification('n2', days_ago=65)
        make_notification('n3', days_ago=10)

        from account.tasks import cleanup_notifications
        result = cleanup_notifications(days=60)
        self.assertIn('2', result)

    def test_cleanup_does_not_affect_recent(self):
        recent = make_notification('recent', days_ago=5)

        from account.tasks import cleanup_notifications
        cleanup_notifications(days=60)

        self.assertTrue(Notification.objects.filter(pk=recent.pk).exists())