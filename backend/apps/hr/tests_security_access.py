from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount, Employee, Department
from account.models_rbac import PermissionProfile, ProfileAssignment
from account.role_permissions import MenuItem
from hr.models import Company


class SecurityAttendanceAccessTest(TestCase):
    """Начальник СБ получает посещаемость всех отделов через профиль, без смены роли."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        company = Company.objects.create(name='SB Co', bin_number='555666777888')
        self.security = Department.objects.create(name='Служба безопасности', company=company)
        other = Department.objects.create(name='Бухгалтерия', company=company)
        self.user = UserAccount.objects.create_user(username='sb_head', password='pass', role='staff')
        Employee.objects.create(user=self.user, department=self.security, status='active')
        colleague = UserAccount.objects.create_user(username='accountant', password='pass', role='staff')
        Employee.objects.create(user=colleague, department=other, status='active')

    def _grant_profile(self):
        ProfileAssignment.objects.create(
            profile=PermissionProfile.objects.get(name='Служба безопасности (просмотр)'),
            scope_type=ProfileAssignment.SCOPE_DEPARTMENT,
            department=self.security,
        )
        cache.clear()

    def test_without_profile_redirected_to_own_attendance(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('hr:attendance_journal'))
        self.assertRedirects(response, reverse('hr:attendance_my'), fetch_redirect_response=False)

    def test_profile_opens_journal_and_registry_for_all_departments(self):
        self._grant_profile()
        self.client.force_login(self.user)

        journal = self.client.get(reverse('hr:attendance_journal'))
        self.assertEqual(journal.status_code, 200)
        self.assertTrue(journal.context['is_hr'])

        registry = self.client.get(reverse('hr:attendance_registry'))
        self.assertEqual(registry.status_code, 200)
        self.assertEqual(len(registry.context['departments']), 2)

    def test_profile_does_not_grant_editing(self):
        self._grant_profile()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('hr:manual_attendance')).status_code, 403)
        self.assertEqual(self.client.get(reverse('hr:companies')).status_code, 403)

    def test_menu_contains_attendance_and_rounds(self):
        self._grant_profile()

        def ids(items):
            out = set()
            for item in items:
                out.add(item.id)
                out |= ids(item.submenu or [])
            return out

        menu_ids = ids(MenuItem.generate_menu(self.user))
        self.assertIn('attendance_journal', menu_ids)
        self.assertIn('rounds_journal', menu_ids)
