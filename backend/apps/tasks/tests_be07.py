from django.test import TestCase, RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

from account.models import UserAccount
from tasks.models import Task


def make_user(username, role='staff'):
    return UserAccount.objects.create_user(username=username, password='test1234', role=role)


def make_task(author, executor=None, title='Test Task'):
    return Task.objects.create(
        author=author,
        executor=executor,
        title=title,
        deadline=timezone.now().date(),
        status='created',
    )


class CanDeletePolicyTest(TestCase):

    def setUp(self):
        self.author = make_user('author1')
        self.other = make_user('other1')
        self.admin = make_user('admin1', role='administrator')
        self.task = make_task(self.author)

    def test_author_can_delete(self):
        self.assertTrue(self.task.can_delete(self.author))

    def test_other_cannot_delete(self):
        self.assertFalse(self.task.can_delete(self.other))

    def test_admin_can_delete(self):
        self.assertTrue(self.task.can_delete(self.admin))

    def test_unauthenticated_cannot_delete(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(self.task.can_delete(AnonymousUser()))


class RestoreTaskTest(TestCase):

    def setUp(self):
        self.author = make_user('author2')
        self.admin = make_user('admin2', role='administrator')
        self.task = make_task(self.author)

    def test_restore_clears_deleted_fields(self):
        self.task.soft_delete(self.author, reason='тест удаления')
        self.assertTrue(self.task.is_deleted)
        self.task.restore()
        self.task.refresh_from_db()
        self.assertIsNone(self.task.deleted_at)
        self.assertIsNone(self.task.deleted_by)
        self.assertEqual(self.task.deleted_reason, '')

    def test_restore_makes_task_visible(self):
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.author
        self.task.executor = self.author
        self.task.save()

        self.task.soft_delete(self.author, reason='тест удаления')
        self.assertEqual(Task.get_available_queryset(request).filter(pk=self.task.pk).count(), 0)

        self.task.restore()
        self.assertEqual(Task.get_available_queryset(request).filter(pk=self.task.pk).count(), 1)


class DeleteAPIReasonValidationTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.author = make_user('author3')
        self.task = make_task(self.author)
        self.client.force_authenticate(user=self.author)

    def test_delete_requires_reason_5_chars(self):
        r = self.client.delete(
            f'/api/v1/tasks/{self.task.pk}/',
            data={'reason': 'ок'},
            format='json',
        )
        self.assertEqual(r.status_code, 400)

    def test_delete_with_valid_reason(self):
        r = self.client.delete(
            f'/api/v1/tasks/{self.task.pk}/',
            data={'reason': 'причина удаления'},
            format='json',
        )
        self.assertEqual(r.status_code, 204)
        self.task.refresh_from_db()
        self.assertTrue(self.task.is_deleted)

    def test_delete_forbidden_for_non_author(self):
        other = make_user('other3')
        self.client.force_authenticate(user=other)
        r = self.client.delete(
            f'/api/v1/tasks/{self.task.pk}/',
            data={'reason': 'причина удаления'},
            format='json',
        )
        self.assertIn(r.status_code, [403, 404])


class RestoreAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin3', role='administrator')
        self.author = make_user('author4')
        self.task = make_task(self.author)
        self.task.soft_delete(self.author, reason='тест удаления')

    def test_admin_can_restore(self):
        self.client.force_authenticate(user=self.admin)
        r = self.client.post(f'/api/v1/tasks/{self.task.pk}/restore/')
        self.assertEqual(r.status_code, 200)
        self.task.refresh_from_db()
        self.assertFalse(self.task.is_deleted)

    def test_non_admin_cannot_restore_others_task(self):
        other = make_user('other4')
        self.client.force_authenticate(user=other)
        r = self.client.post(f'/api/v1/tasks/{self.task.pk}/restore/')
        self.assertIn(r.status_code, [403, 404])