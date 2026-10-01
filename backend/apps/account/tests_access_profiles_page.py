from django.test import TestCase
from django.urls import reverse

from account.models import Department, UserAccount
from account.models_rbac import PermissionProfile, ProfileAssignment
from hr.models import Position


class AccessProfilesPageTest(TestCase):
    """Страница профилей доступа: что показано и что отдано в окно назначения."""

    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            username='admin1', password='pwd', role='administrator', is_superuser=True
        )
        self.client.force_login(self.admin)

        self.department = Department.objects.create(name='Эксплуатация')
        self.position = Position.objects.create(
            title='Кладовщик', department=self.department
        )

        self.profile = PermissionProfile.objects.create(name='Кладовщик: склад')

    def _get(self):
        return self.client.get(reverse('account:access_profiles'))

    def test_positions_are_available_for_assignment(self):
        html = self._get().content.decode()
        self.assertIn('ACCESS_POSITIONS', html)
        # Отдел в подписи обязателен: должности уникальны только внутри него.
        self.assertIn('Кладовщик — Эксплуатация', html)

    def test_position_assignment_is_visible_in_the_list(self):
        ProfileAssignment.objects.create(
            profile=self.profile,
            scope_type=ProfileAssignment.SCOPE_POSITION,
            position=self.position,
        )
        html = self._get().content.decode()
        self.assertIn('Должность: Кладовщик', html)

    def test_profile_without_bindings_shows_a_dash(self):
        html = self._get().content.decode()
        self.assertNotIn('Должность:', html.split('ACCESS_POSITIONS')[0])
