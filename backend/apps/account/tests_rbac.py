from django.core.cache import cache
from django.test import TestCase

from account.models import Department, Employee, UserAccount
from account.models_rbac import (
    AppPermission,
    PermissionProfile,
    ProfileAssignment,
    UserPermissionOverride,
)
from account.role_permissions import PermissionEnums, RolePermissions
from account.services.permissions import (
    invalidate_role_cache,
    role_has_permission,
    user_has_permission,
)
from hr.models import Position


def _seed():
    for perm in PermissionEnums:
        AppPermission.objects.get_or_create(code=perm.value, defaults={'label': perm.value})
    for role, perms in RolePermissions.permissions.items():
        profile, _ = PermissionProfile.objects.get_or_create(
            role=role, defaults={'name': role, 'is_system': True}
        )
        perm_objs = AppPermission.objects.filter(code__in=[p.value for p in perms])
        profile.permissions.set(perm_objs)


class RolePermissionParityTest(TestCase):
    def setUp(self):
        _seed()

    def test_every_role_matches_static_map(self):
        for role, perms in RolePermissions.permissions.items():
            expected = {p.value for p in perms}
            profile = PermissionProfile.objects.get(role=role)
            got = set(profile.permissions.values_list('code', flat=True))
            self.assertEqual(got, expected, f'mismatch for role={role}')

    def test_catalog_covers_all_enum_permissions(self):
        enum_codes = {p.value for p in PermissionEnums}
        db_codes = set(AppPermission.objects.values_list('code', flat=True))
        self.assertTrue(enum_codes.issubset(db_codes))

    def test_role_has_permission_matches_check_permission(self):
        for role in RolePermissions.permissions:
            for perm in PermissionEnums:
                self.assertEqual(
                    role_has_permission(role, perm),
                    RolePermissions.checkPermission(role, perm),
                    f'role={role} perm={perm.value}',
                )


class OverridePriorityTest(TestCase):
    def setUp(self):
        cache.clear()
        _seed()
        self.staff = UserAccount.objects.create(username='staff1', role='staff')

    def _perm(self, code):
        return AppPermission.objects.get(code=code)

    def test_role_baseline(self):
        self.assertTrue(user_has_permission(self.staff, PermissionEnums.TASKS))
        self.assertFalse(user_has_permission(self.staff, PermissionEnums.FINANCES))

    def test_allow_override_grants_extra_permission(self):
        UserPermissionOverride.objects.create(
            user=self.staff, permission=self._perm('finances'), effect='ALLOW'
        )
        self.assertTrue(user_has_permission(self.staff, PermissionEnums.FINANCES))

    def test_deny_override_revokes_role_permission(self):
        UserPermissionOverride.objects.create(
            user=self.staff, permission=self._perm('tasks'), effect='DENY'
        )
        self.assertFalse(user_has_permission(self.staff, PermissionEnums.TASKS))

    def test_deny_beats_allow_is_moot_by_unique_but_deny_wins_semantically(self):
        UserPermissionOverride.objects.create(
            user=self.staff, permission=self._perm('dashboard'), effect='DENY'
        )
        self.assertFalse(user_has_permission(self.staff, PermissionEnums.DASHBOARD))

    def test_superuser_bypasses_everything(self):
        su = UserAccount.objects.create(username='root', role='guest', is_superuser=True)
        UserPermissionOverride.objects.create(
            user=su, permission=self._perm('finances'), effect='DENY'
        )
        self.assertTrue(user_has_permission(su, PermissionEnums.FINANCES))


class CacheInvalidationTest(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        _seed()

    def test_profile_change_invalidates_cache(self):
        self.assertFalse(role_has_permission('staff', PermissionEnums.FINANCES))
        profile = PermissionProfile.objects.get(role='staff')
        profile.permissions.add(AppPermission.objects.get(code='finances'))
        invalidate_role_cache('staff')
        self.assertTrue(role_has_permission('staff', PermissionEnums.FINANCES))


class ProfileAssignmentScopeTest(TestCase):
    """Профиль прав, назначенный на группу людей, а не на конкретного человека."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        _seed()

        self.department = Department.objects.create(name='Эксплуатация')
        self.other_department = Department.objects.create(name='Бухгалтерия')
        self.storekeeper = Position.objects.create(
            title='Кладовщик', department=self.department
        )
        # Одноимённая должность в другом отделе — отдельная запись, и права
        # на неё не должны распространяться.
        self.other_storekeeper = Position.objects.create(
            title='Кладовщик', department=self.other_department
        )

        self.profile = PermissionProfile.objects.create(name='Кладовщик: склад')
        self.profile.permissions.set(
            AppPermission.objects.filter(code__in=['purchases', 'suppliers'])
        )

    def _employee(self, username, position=None, department=None):
        user = UserAccount.objects.create(username=username, role='staff')
        Employee.objects.create(
            user=user,
            department=department or self.department,
            position=position,
        )
        return user

    def _assign_to_position(self, position):
        return ProfileAssignment.objects.create(
            profile=self.profile,
            scope_type=ProfileAssignment.SCOPE_POSITION,
            position=position,
        )

    def test_position_assignment_grants_permission(self):
        user = self._employee('keeper', position=self.storekeeper)
        self.assertFalse(user_has_permission(user, PermissionEnums.PURCHASES))

        self._assign_to_position(self.storekeeper)
        self.assertTrue(user_has_permission(user, PermissionEnums.PURCHASES))
        self.assertTrue(user_has_permission(user, PermissionEnums.SUPPLIERS))

    def test_same_title_in_another_department_is_not_affected(self):
        ours = self._employee('keeper', position=self.storekeeper)
        theirs = self._employee(
            'keeper2',
            position=self.other_storekeeper,
            department=self.other_department,
        )
        self._assign_to_position(self.storekeeper)

        self.assertTrue(user_has_permission(ours, PermissionEnums.PURCHASES))
        self.assertFalse(user_has_permission(theirs, PermissionEnums.PURCHASES))

    def test_employee_without_position_is_not_affected(self):
        user = self._employee('nobody')
        self._assign_to_position(self.storekeeper)
        self.assertFalse(user_has_permission(user, PermissionEnums.PURCHASES))

    def test_personal_deny_beats_position_assignment(self):
        user = self._employee('keeper', position=self.storekeeper)
        self._assign_to_position(self.storekeeper)
        UserPermissionOverride.objects.create(
            user=user,
            permission=AppPermission.objects.get(code='purchases'),
            effect='DENY',
        )
        self.assertFalse(user_has_permission(user, PermissionEnums.PURCHASES))

    def test_revoking_assignment_takes_effect(self):
        user = self._employee('keeper', position=self.storekeeper)
        assignment = self._assign_to_position(self.storekeeper)
        self.assertTrue(user_has_permission(user, PermissionEnums.PURCHASES))

        assignment.delete()
        self.assertFalse(user_has_permission(user, PermissionEnums.PURCHASES))

    def test_department_assignment_still_works(self):
        user = self._employee('any', position=self.storekeeper)
        ProfileAssignment.objects.create(
            profile=self.profile,
            scope_type=ProfileAssignment.SCOPE_DEPARTMENT,
            department=self.department,
        )
        self.assertTrue(user_has_permission(user, PermissionEnums.PURCHASES))