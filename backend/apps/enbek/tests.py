from django.test import TestCase, Client
from django.urls import reverse, resolve

from enbek import views


class EnbekApiTestCase(TestCase):
    def setUp(self):
        self.client = Client()

    def test_login_url_resolves_correctly(self):
        resolver = resolve('/api/enbek/auth/login/')
        self.assertEqual(resolver.func, views.login)

    def test_contracts_url_resolves_correctly(self):
        resolver = resolve('/api/enbek/contracts/')
        self.assertEqual(resolver.func, views.contracts)

    def test_leaves_url_resolves_correctly(self):
        resolver = resolve('/api/enbek/leaves/')
        self.assertEqual(resolver.func, views.leaves)

    def test_sick_leaves_url_resolves_correctly(self):
        resolver = resolve('/api/enbek/sick-leaves/')
        self.assertEqual(resolver.func, views.sick_leaves)

    def test_login_returns_access_token(self):
        response = self.client.post(
            '/api/enbek/auth/login/',
            data={},
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('access_token', data)
        self.assertIn('token_type', data)
        self.assertIn('expires_in', data)

        self.assertEqual(data['access_token'], 'mock_token_123')
        self.assertEqual(data['token_type'], 'Bearer')
        self.assertEqual(data['expires_in'], 3600)

    def test_login_only_allows_post(self):
        response = self.client.get('/api/enbek/auth/login/')
        self.assertNotEqual(response.status_code, 200)

    def test_contracts_returns_json_list(self):
        response = self.client.get('/api/enbek/contracts/')

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)

        contract = data[0]
        self.assertIn('id', contract)
        self.assertIn('employee_name', contract)
        self.assertIn('position', contract)
        self.assertIn('start_date', contract)
        self.assertIn('status', contract)

        self.assertEqual(contract['employee_name'], 'Иван Иванов')
        self.assertEqual(contract['position'], 'Frontend Developer')
        self.assertEqual(contract['start_date'], '2024-01-10')
        self.assertEqual(contract['status'], 'active')

    def test_leaves_returns_json_list(self):
        response = self.client.get('/api/enbek/leaves/')

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)

        leave = data[0]
        self.assertIn('id', leave)
        self.assertIn('employee_name', leave)
        self.assertIn('type', leave)
        self.assertIn('start_date', leave)
        self.assertIn('end_date', leave)
        self.assertIn('status', leave)

        self.assertEqual(leave['employee_name'], 'Иван Иванов')
        self.assertEqual(leave['type'], 'annual')
        self.assertEqual(leave['start_date'], '2024-06-01')
        self.assertEqual(leave['end_date'], '2024-06-14')
        self.assertEqual(leave['status'], 'approved')

    def test_sick_leaves_returns_json_list(self):
        response = self.client.get('/api/enbek/sick-leaves/')

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)

        sick_leave = data[0]
        self.assertIn('id', sick_leave)
        self.assertIn('employee_name', sick_leave)
        self.assertIn('start_date', sick_leave)
        self.assertIn('end_date', sick_leave)
        self.assertIn('status', sick_leave)

        self.assertEqual(sick_leave['employee_name'], 'Иван Иванов')
        self.assertEqual(sick_leave['start_date'], '2024-03-01')
        self.assertEqual(sick_leave['end_date'], '2024-03-05')
        self.assertEqual(sick_leave['status'], 'closed')