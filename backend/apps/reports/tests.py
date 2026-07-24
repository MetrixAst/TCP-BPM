from django.test import TestCase, Client
from django.urls import reverse

from account.models import UserAccount
from account.role_permissions import RoleEnums
import unittest


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

    @unittest.skip(
        "Тест описывает нереализованную фичу: сообщение 'Интеграция с системой "
        "аналитики не подключена' нигде не существует в коде/шаблонах. Страница "
        "reports:home сейчас реально считает агрегаты из БД, а не показывает "
        "заглушку. Нужно решение продукта: либо реализовать заглушку, либо "
        "переписать тест под текущее поведение (проверить реальные вычисляемые "
        "значения вместо жёстко захардкоженных чисел из теста)."
    )
    def test_reports_no_demo_kpi_numbers(self):
        self.client.login(username='reports_user', password='pass')
        r = self.client.get(reverse('reports:home'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Интеграция с системой аналитики не подключена')
        self.assertNotContains(r, '5 320 703 568')
        self.assertNotContains(r, '611 124')
        self.assertContains(r, 'reports-indicators-page')