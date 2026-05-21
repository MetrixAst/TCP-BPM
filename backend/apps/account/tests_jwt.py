from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import UserAccount
from account.role_permissions import RoleEnums


class JWTAuthAPITestCase(APITestCase):
    def setUp(self):
        self.password = 'jwt-secret-pass'
        self.user = UserAccount.objects.create_user(
            username='jwt_user',
            password=self.password,
            role=RoleEnums.STAFF.value,
        )
        self.token_url = reverse('token_obtain_pair')
        self.refresh_url = reverse('token_refresh')
        self.tasks_url = reverse('task-list')

    def test_obtain_pair_success(self):
        response = self.client.post(
            self.token_url,
            {'username': 'jwt_user', 'password': self.password},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_obtain_pair_invalid_credentials(self):
        response = self.client.post(
            self.token_url,
            {'username': 'jwt_user', 'password': 'wrong'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_returns_new_access(self):
        obtain = self.client.post(
            self.token_url,
            {'username': 'jwt_user', 'password': self.password},
            format='json',
        )
        refresh_token = obtain.data['refresh']
        response = self.client.post(
            self.refresh_url,
            {'refresh': refresh_token},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_api_v1_with_bearer_token(self):
        obtain = self.client.post(
            self.token_url,
            {'username': 'jwt_user', 'password': self.password},
            format='json',
        )
        access = obtain.data['access']
        response = self.client.get(
            self.tasks_url,
            HTTP_AUTHORIZATION=f'Bearer {access}',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
