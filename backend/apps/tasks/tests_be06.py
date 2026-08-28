from django.test import TestCase, RequestFactory
from django.utils import timezone

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


class SoftDeleteTaskTest(TestCase):

    def setUp(self):
        self.user = make_user('user1')
        self.other = make_user('user2')
        self.task = make_task(self.user)

    def test_soft_delete_sets_fields(self):
        self.task.soft_delete(self.user, reason='тест')
        self.task.refresh_from_db()
        self.assertIsNotNone(self.task.deleted_at)
        self.assertEqual(self.task.deleted_by, self.user)
        self.assertEqual(self.task.deleted_reason, 'тест')

    def test_is_deleted_property(self):
        self.assertFalse(self.task.is_deleted)
        self.task.soft_delete(self.user)
        self.task.refresh_from_db()
        self.assertTrue(self.task.is_deleted)

    def test_deleted_excluded_from_queryset(self):
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        self.task.executor = self.user
        self.task.save()

        count_before = Task.get_available_queryset(request).count()
        self.task.soft_delete(self.user)
        count_after = Task.get_available_queryset(request).count()
        self.assertEqual(count_after, count_before - 1)

    def test_deleted_excluded_from_statistic(self):
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        self.task.executor = self.user
        self.task.save()

        stats_before = sum(s['count'] for s in Task.get_statistic(request))
        self.task.soft_delete(self.user)
        stats_after = sum(s['count'] for s in Task.get_statistic(request))
        self.assertEqual(stats_after, stats_before - 1)

    def test_deleted_excluded_from_search(self):
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        self.task.executor = self.user
        self.task.save()

        self.task.soft_delete(self.user)
        qs = Task.get_available_queryset(request).filter(title__icontains='Test Task')
        self.assertEqual(qs.count(), 0)

    def test_task_remains_in_db_after_soft_delete(self):
        self.task.soft_delete(self.user)
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())