from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from account.models import UserAccount
from account.models_rbac import AppPermission, PermissionProfile, UserPermissionOverride, PermissionAuditLog


def make_user(username, role, password='test1234'):
    u = UserAccount.objects.create_user(username=username, password=password, role=role)
    return u


class AuditLogSignalTest(TestCase):
    def setUp(self):
        self.admin = make_user('admin_test', 'administrator')
        self.staff = make_user('staff_test', 'staff')
        self.perm = AppPermission.objects.get(code='dashboard')

    def test_override_add_creates_audit(self):
        override = UserPermissionOverride.objects.create(
            user=self.staff,
            permission=self.perm,
            effect='ALLOW',
            created_by=self.admin,
        )
        self.assertTrue(
            PermissionAuditLog.objects.filter(
                action=PermissionAuditLog.ACTION_OVERRIDE_ADD,
                target_user=self.staff,
                permission_code='dashboard',
            ).exists()
        )

    def test_override_delete_creates_audit(self):
        override = UserPermissionOverride.objects.create(
            user=self.staff,
            permission=self.perm,
            effect='ALLOW',
            created_by=self.admin,
        )
        override.delete()
        self.assertTrue(
            PermissionAuditLog.objects.filter(
                action=PermissionAuditLog.ACTION_OVERRIDE_DELETE,
                target_user=self.staff,
                permission_code='dashboard',
            ).exists()
        )

    def test_profile_grant_creates_audit(self):
        profile = PermissionProfile.objects.get(role='staff')
        perm = AppPermission.objects.get(code='reports')
        initial_count = PermissionAuditLog.objects.filter(
            action=PermissionAuditLog.ACTION_GRANT,
            permission_code='reports',
        ).count()
        profile.permissions.add(perm)
        self.assertEqual(
            PermissionAuditLog.objects.filter(
                action=PermissionAuditLog.ACTION_GRANT,
                permission_code='reports',
            ).count(),
            initial_count + 1,
        )


class RoleAccessRegressionTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.roles = [
            'administrator', 'hr', 'staff', 'guest',
            'tenant', 'owner', 'cfo', 'chief_accountant',
        ]
        self.users = {}
        for role in self.roles:
            self.users[role] = make_user(f'user_{role}', role)

    def _auth(self, role):
        self.client.force_authenticate(user=self.users[role])

    def test_audit_log_only_admin(self):
        self._auth('administrator')
        r = self.client.get('/api/v1/permissions/audit/')
        self.assertEqual(r.status_code, 200)

        for role in ['hr', 'staff', 'guest', 'tenant', 'owner', 'cfo', 'chief_accountant']:
            self._auth(role)
            r = self.client.get('/api/v1/permissions/audit/')
            self.assertIn(r.status_code, [403, 401], msg=f'{role} не должен видеть аудит')

    def test_permissions_catalog_only_admin(self):
        self._auth('administrator')
        r = self.client.get('/api/v1/permissions/catalog/')
        self.assertEqual(r.status_code, 200)

        for role in ['hr', 'staff', 'guest', 'tenant']:
            self._auth(role)
            r = self.client.get('/api/v1/permissions/catalog/')
            self.assertIn(r.status_code, [403, 401])

    def test_permissions_profiles_only_admin(self):
        self._auth('administrator')
        r = self.client.get('/api/v1/permissions/profiles/')
        self.assertEqual(r.status_code, 200)

        for role in ['hr', 'staff', 'guest', 'tenant']:
            self._auth(role)
            r = self.client.get('/api/v1/permissions/profiles/')
            self.assertIn(r.status_code, [403, 401])

    def test_permissions_users_only_admin(self):
        self._auth('administrator')
        r = self.client.get('/api/v1/permissions/users/')
        self.assertEqual(r.status_code, 200)

        for role in ['hr', 'staff', 'guest', 'tenant']:
            self._auth(role)
            r = self.client.get('/api/v1/permissions/users/')
            self.assertIn(r.status_code, [403, 401])


class AuditLogAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_audit', 'administrator')
        self.staff = make_user('staff_audit', 'staff')
        self.perm = AppPermission.objects.get(code='dashboard')
        self.client.force_authenticate(user=self.admin)

    def test_audit_log_list(self):
        UserPermissionOverride.objects.create(
            user=self.staff,
            permission=self.perm,
            effect='ALLOW',
            created_by=self.admin,
        )
        r = self.client.get('/api/v1/permissions/audit/')
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.data['results']), 0)

    def test_audit_log_filter_by_user(self):
        UserPermissionOverride.objects.create(
            user=self.staff,
            permission=self.perm,
            effect='ALLOW',
            created_by=self.admin,
        )
        r = self.client.get(f'/api/v1/permissions/audit/?user_id={self.staff.pk}')
        self.assertEqual(r.status_code, 200)
        for item in r.data['results']:
            self.assertEqual(item['target_user'], self.staff.pk)