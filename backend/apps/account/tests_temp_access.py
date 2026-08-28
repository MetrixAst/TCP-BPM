from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from account.models import UserAccount
from account.models_rbac import AppPermission, TemporaryAccess, PermissionAuditLog


def make_user(username, role='staff'):
    return UserAccount.objects.create_user(username=username, password='pass', role=role)


class TemporaryAccessModelTest(TestCase):

    def setUp(self):
        self.admin = make_user('admin_ta', role='administrator')
        self.staff = make_user('staff_ta', role='staff')
        self.perm = AppPermission.objects.get(code='dashboard')

    def test_is_active_when_in_range(self):
        access = TemporaryAccess.objects.create(
            user=self.staff,
            permission=self.perm,
            date_from=timezone.now() - timedelta(hours=1),
            date_to=timezone.now() + timedelta(hours=1),
            reason='тест',
            granted_by=self.admin,
        )
        self.assertTrue(access.is_active)

    def test_is_not_active_when_expired(self):
        access = TemporaryAccess.objects.create(
            user=self.staff,
            permission=self.perm,
            date_from=timezone.now() - timedelta(hours=2),
            date_to=timezone.now() - timedelta(hours=1),
            reason='тест',
            granted_by=self.admin,
        )
        self.assertFalse(access.is_active)

    def test_is_not_active_when_revoked(self):
        access = TemporaryAccess.objects.create(
            user=self.staff,
            permission=self.perm,
            date_from=timezone.now() - timedelta(hours=1),
            date_to=timezone.now() + timedelta(hours=1),
            reason='тест',
            status=TemporaryAccess.STATUS_REVOKED,
            granted_by=self.admin,
        )
        self.assertFalse(access.is_active)


class TemporaryAccessPermissionTest(TestCase):

    def setUp(self):
        self.admin = make_user('admin_tap', role='administrator')
        self.staff = make_user('staff_tap', role='staff')
        self.perm = AppPermission.objects.get(code='finances')

    def test_temporary_access_grants_permission(self):
        from account.services.permissions import user_has_permission
        from account.role_permissions import PermissionEnums
        self.assertFalse(user_has_permission(self.staff, PermissionEnums.FINANCES))

        TemporaryAccess.objects.create(
            user=self.staff,
            permission=self.perm,
            date_from=timezone.now() - timedelta(hours=1),
            date_to=timezone.now() + timedelta(hours=1),
            reason='временный доступ к финансам',
            granted_by=self.admin,
        )
        self.assertTrue(user_has_permission(self.staff, PermissionEnums.FINANCES))

    def test_expired_temporary_access_denies_permission(self):
        from account.services.permissions import user_has_permission
        from account.role_permissions import PermissionEnums
        TemporaryAccess.objects.create(
            user=self.staff,
            permission=self.perm,
            date_from=timezone.now() - timedelta(hours=2),
            date_to=timezone.now() - timedelta(hours=1),
            reason='истёкший доступ',
            granted_by=self.admin,
        )
        self.assertFalse(user_has_permission(self.staff, PermissionEnums.FINANCES))


class TemporaryAccessAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_api_ta', role='administrator')
        self.staff = make_user('staff_api_ta', role='staff')
        self.perm = AppPermission.objects.get(code='dashboard')
        self.client.force_authenticate(user=self.admin)

    def test_create_temporary_access(self):
        r = self.client.post('/api/v1/permissions/temporary/', {
            'user': self.staff.pk,
            'permission': self.perm.pk,
            'date_from': (timezone.now() - timedelta(hours=1)).isoformat(),
            'date_to': (timezone.now() + timedelta(hours=24)).isoformat(),
            'reason': 'тест временного доступа',
        }, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(TemporaryAccess.objects.filter(user=self.staff).exists())

    def test_create_logs_audit(self):
        self.client.post('/api/v1/permissions/temporary/', {
            'user': self.staff.pk,
            'permission': self.perm.pk,
            'date_from': (timezone.now() - timedelta(hours=1)).isoformat(),
            'date_to': (timezone.now() + timedelta(hours=24)).isoformat(),
            'reason': 'тест аудита',
        }, format='json')
        self.assertTrue(PermissionAuditLog.objects.filter(
            target_user=self.staff,
            action='GRANT',
        ).exists())

    def test_revoke_access(self):
        access = TemporaryAccess.objects.create(
            user=self.staff,
            permission=self.perm,
            date_from=timezone.now() - timedelta(hours=1),
            date_to=timezone.now() + timedelta(hours=24),
            reason='тест отзыва',
            granted_by=self.admin,
        )
        r = self.client.post(f'/api/v1/permissions/temporary/{access.pk}/revoke/')
        self.assertEqual(r.status_code, 200)
        access.refresh_from_db()
        self.assertEqual(access.status, TemporaryAccess.STATUS_REVOKED)
        self.assertEqual(access.revoked_by, self.admin)

    def test_extend_access(self):
        access = TemporaryAccess.objects.create(
            user=self.staff,
            permission=self.perm,
            date_from=timezone.now() - timedelta(hours=1),
            date_to=timezone.now() + timedelta(hours=24),
            reason='тест продления',
            granted_by=self.admin,
        )
        new_date_to = (timezone.now() + timedelta(days=7)).isoformat()
        r = self.client.patch(f'/api/v1/permissions/temporary/{access.pk}/extend/', {
            'date_to': new_date_to,
        }, format='json')
        self.assertEqual(r.status_code, 200)

    def test_extend_with_naive_datetime_local_input(self):
        # Браузерный <input type="datetime-local"> отдаёт строку без смещения
        # часового пояса (например "2026-08-29T18:00") — именно так шлёт
        # реальный FE. datetime.fromisoformat() на такой строке даёт naive
        # datetime, а timezone.now() — aware; их сравнение падало с
        # TypeError вместо корректного ответа.
        access = TemporaryAccess.objects.create(
            user=self.staff,
            permission=self.perm,
            date_from=timezone.now() - timedelta(hours=1),
            date_to=timezone.now() + timedelta(hours=24),
            reason='тест продления без таймзоны',
            granted_by=self.admin,
        )
        naive_date_to = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M')
        r = self.client.patch(f'/api/v1/permissions/temporary/{access.pk}/extend/', {
            'date_to': naive_date_to,
        }, format='json')
        self.assertEqual(r.status_code, 200)

    def test_invalid_date_range(self):
        r = self.client.post('/api/v1/permissions/temporary/', {
            'user': self.staff.pk,
            'permission': self.perm.pk,
            'date_from': (timezone.now() + timedelta(hours=2)).isoformat(),
            'date_to': (timezone.now() + timedelta(hours=1)).isoformat(),
            'reason': 'неверный диапазон',
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_staff_cannot_create(self):
        self.client.force_authenticate(user=self.staff)
        r = self.client.post('/api/v1/permissions/temporary/', {
            'user': self.staff.pk,
            'permission': self.perm.pk,
            'date_from': (timezone.now()).isoformat(),
            'date_to': (timezone.now() + timedelta(hours=24)).isoformat(),
            'reason': 'тест',
        }, format='json')
        self.assertIn(r.status_code, [403, 401])

    def test_historical_data_preserved(self):
        access = TemporaryAccess.objects.create(
            user=self.staff,
            permission=self.perm,
            date_from=timezone.now() - timedelta(hours=2),
            date_to=timezone.now() - timedelta(hours=1),
            reason='исторический доступ',
            status=TemporaryAccess.STATUS_EXPIRED,
            granted_by=self.admin,
        )
        self.assertTrue(TemporaryAccess.objects.filter(pk=access.pk).exists())


class ExpireTemporaryAccessTaskTest(TestCase):

    def setUp(self):
        self.admin = make_user('admin_task_ta', role='administrator')
        self.staff = make_user('staff_task_ta', role='staff')
        self.perm = AppPermission.objects.get(code='dashboard')

    def test_expire_task_updates_status(self):
        access = TemporaryAccess.objects.create(
            user=self.staff,
            permission=self.perm,
            date_from=timezone.now() - timedelta(hours=2),
            date_to=timezone.now() - timedelta(hours=1),
            reason='истёкший доступ',
            granted_by=self.admin,
        )
        from account.tasks import expire_temporary_accesses
        expire_temporary_accesses()
        access.refresh_from_db()
        self.assertEqual(access.status, TemporaryAccess.STATUS_EXPIRED)