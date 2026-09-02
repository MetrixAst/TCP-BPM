from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount
from account.role_permissions import RoleEnums
from ecopark.models import EcoWork


class EcoParkAccessTest(TestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            username='eco_admin',
            password='pass',
            email='eco@test.local',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.work = EcoWork.objects.create(title='Проверка вентиляции')

    def test_home_requires_login(self):
        response = self.client.get(reverse('ecopark:home'))

        self.assertEqual(response.status_code, 302)

    def test_authorized_user_can_open_home(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('ecopark:home'))

        self.assertEqual(response.status_code, 200)

    def test_delete_rejects_get(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('ecopark:delete', args=[self.work.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(EcoWork.objects.filter(pk=self.work.pk).exists())
