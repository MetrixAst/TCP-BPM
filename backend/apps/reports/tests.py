from django.test import TestCase, Client
from django.urls import reverse

from account.models import UserAccount
from account.role_permissions import RoleEnums


class ReportsIndicatorsViewTest(TestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            username='reports_user',
            password='pass',
            email='reports@test.local',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.client = Client()

    def test_reports_requires_login(self):
        r = self.client.get(reverse('reports:home'))
        self.assertEqual(r.status_code, 302)

    def test_reports_no_demo_kpi_numbers(self):
        self.client.login(username='reports_user', password='pass')
        r = self.client.get(reverse('reports:home'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Интеграция с системой аналитики не подключена')
        self.assertNotContains(r, '5 320 703 568')
        self.assertNotContains(r, '611 124')
        self.assertContains(r, 'reports-indicators-page')
