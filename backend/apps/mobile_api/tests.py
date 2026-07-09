from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import PushToken, UserAccount


class MobileApiMeTests(APITestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            username='mobiletest',
            password='testpass123',
            role='staff',
            first_name='Иван',
            last_name='Иванов',
        )
        self.url = reverse('mobile_api:me')

    def test_me_without_token_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_with_auth_returns_profile(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['profile']['username'], 'mobiletest')

    def test_me_returns_menu(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertIsInstance(response.data['menu'], list)

    def test_me_returns_badges(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertIn('counts', response.data['badges'])
        self.assertIn('indicators', response.data['badges'])


class MobileApiDevicesTests(APITestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            username='devicetest',
            password='testpass123',
            role='staff',
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse('mobile_api:devices')

    def test_devices_post_creates_token(self):
        response = self.client.post(self.url, {'fcm': 'token-abc-123'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PushToken.objects.filter(user=self.user).count(), 1)

    def test_devices_post_is_idempotent(self):
        self.client.post(self.url, {'fcm': 'token-abc-123'})
        self.client.post(self.url, {'fcm': 'token-abc-123'})
        self.assertEqual(PushToken.objects.filter(user=self.user).count(), 1)

    def test_devices_delete_by_token(self):
        PushToken.objects.create(user=self.user, fcm='token-1')
        PushToken.objects.create(user=self.user, fcm='token-2')
        response = self.client.delete(self.url, {'fcm': 'token-1'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(PushToken.objects.filter(fcm='token-1').exists())
        self.assertEqual(PushToken.objects.filter(user=self.user).count(), 1)

    def test_devices_delete_all_on_logout(self):
        PushToken.objects.create(user=self.user, fcm='token-1')
        PushToken.objects.create(user=self.user, fcm='token-2')
        response = self.client.delete(self.url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(PushToken.objects.filter(user=self.user).count(), 0)