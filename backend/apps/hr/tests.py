from unittest.mock import Mock, patch
import requests

from django.test import TestCase, override_settings

from hr.enbek_client import (
    EnbekClient,
    EnbekClientError,
    AuthenticationError,
    ConnectionError,
)


@override_settings(
    ENBEK_BASE_URL='http://testserver/api/enbek',
    ENBEK_USERNAME='test_user',
    ENBEK_PASSWORD='test_password',
    ENBEK_TIMEOUT=5,
)
class EnbekClientTestCase(TestCase):
    def setUp(self):
        self.client = EnbekClient()

    def test_authenticate_with_valid_credentials_returns_token(self):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "mock_token_123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch.object(self.client.session, 'post', return_value=mock_response) as mock_post:
            token = self.client.authenticate()

        self.assertEqual(token, "mock_token_123")
        self.assertEqual(self.client.token, "mock_token_123")

        mock_post.assert_called_once_with(
            'http://testserver/api/enbek/auth/login/',
            json={
                'username': 'test_user',
                'password': 'test_password',
            },
            headers={
                'Content-Type': 'application/json',
                'Host': 'localhost',
            },
            timeout=5,
        )

    def test_authenticate_with_invalid_credentials_raises_authentication_error(self):
        mock_response = Mock()
        mock_response.status_code = 401

        with patch.object(self.client.session, 'post', return_value=mock_response):
            with self.assertRaises(AuthenticationError):
                self.client.authenticate()

    def test_get_vacations_returns_list(self):
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            "access_token": "mock_token_123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        vacations_response = Mock()
        vacations_response.status_code = 200
        vacations_response.json.return_value = [
            {
                "id": 1,
                "employee_name": "Иван Иванов",
                "type": "annual",
                "start_date": "2024-06-01",
                "end_date": "2024-06-14",
                "status": "approved",
            }
        ]

        with patch.object(self.client.session, 'post', return_value=auth_response):
            with patch.object(self.client.session, 'get', return_value=vacations_response) as mock_get:
                vacations = self.client.get_vacations()

        self.assertIsInstance(vacations, list)
        self.assertEqual(len(vacations), 1)
        self.assertEqual(vacations[0]['id'], 1)
        self.assertEqual(vacations[0]['employee_name'], 'Иван Иванов')
        self.assertEqual(vacations[0]['type'], 'annual')

        mock_get.assert_called_once_with(
            'http://testserver/api/enbek/leaves/',
            headers={
                'Content-Type': 'application/json',
                'Host': 'localhost',
                'Authorization': 'Bearer mock_token_123',
            },
            timeout=5,
        )

    def test_get_sick_leaves_empty_response_returns_empty_list(self):
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            "access_token": "mock_token_123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        sick_leaves_response = Mock()
        sick_leaves_response.status_code = 200
        sick_leaves_response.json.return_value = []

        with patch.object(self.client.session, 'post', return_value=auth_response):
            with patch.object(self.client.session, 'get', return_value=sick_leaves_response):
                sick_leaves = self.client.get_sick_leaves()

        self.assertIsInstance(sick_leaves, list)
        self.assertEqual(sick_leaves, [])

    def test_timeout_when_api_unavailable_raises_connection_error_with_retry_case(self):
        with patch.object(
            self.client.session,
            'post',
            side_effect=requests.exceptions.Timeout
        ):
            with self.assertRaises(ConnectionError):
                self.client.authenticate()

    def test_handle_response_with_invalid_json_raises_enbek_client_error(self):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError('Invalid JSON')

        with self.assertRaises(EnbekClientError):
            self.client._handle_response(mock_response)

    def test_authenticate_without_token_in_response_raises_authentication_error(self):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch.object(self.client.session, 'post', return_value=mock_response):
            with self.assertRaises(AuthenticationError):
                self.client.authenticate()

    def test_server_error_raises_connection_error(self):
        mock_response = Mock()
        mock_response.status_code = 500

        with self.assertRaises(ConnectionError):
            self.client._handle_response(mock_response)

    def test_client_error_raises_enbek_client_error(self):
        mock_response = Mock()
        mock_response.status_code = 404

        with self.assertRaises(EnbekClientError):
            self.client._handle_response(mock_response)