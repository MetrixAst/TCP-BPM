from datetime import date, timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import UserAccount
from account.role_permissions import RoleEnums
from ecopark.models import EcoWork
from tickets.models import ServiceRequest


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

    def test_cfo_can_open_reports_from_its_menu(self):
        cfo = UserAccount.objects.create_user(
            username='reports_cfo',
            password='pass',
            email='cfo@test.local',
            role=RoleEnums.CFO.value,
        )
        self.client.force_login(cfo)

        response = self.client.get(reverse('reports:home'))

        self.assertEqual(response.status_code, 200)

    def test_period_scopes_ticket_and_exploitation_kpis(self):
        recent_work = EcoWork.objects.create(title='Recent', status='progress')
        old_work = EcoWork.objects.create(title='Old', status='done')
        EcoWork.objects.filter(pk=old_work.pk).update(date=date.today() - timedelta(days=30))

        recent_ticket = ServiceRequest.objects.create(
            title='Recent request', description='Recent', status='new',
        )
        old_ticket = ServiceRequest.objects.create(
            title='Old request', description='Old', status='new',
        )
        ServiceRequest.objects.filter(pk=old_ticket.pk).update(
            created_at=timezone.now() - timedelta(days=30)
        )
        self.assertIsNotNone(recent_work.pk)
        self.assertIsNotNone(recent_ticket.pk)

        self.client.force_login(self.user)
        response = self.client.get(reverse('reports:home'), {'period': 7})

        self.assertEqual(response.status_code, 200)
        cards = {card['label']: card for card in response.context['kpi_cards']}
        self.assertEqual(cards['Эксплуатация']['value'], '1')
        self.assertIn('в работе: 1', cards['Эксплуатация']['sub'])
        self.assertEqual(cards['Заявки (открытые)']['value'], '1')
        self.assertEqual(
            response.context['tickets_status_rows'],
            [{'status': 'Новая', 'count': 1}],
        )
        self.assertEqual(
            response.context['eco_status_rows'],
            [{'status': 'В работе', 'count': 1}],
        )