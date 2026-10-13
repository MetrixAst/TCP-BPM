import hashlib
import hmac
from unittest import mock

from django.test import TestCase, override_settings

from account.models import UserAccount
from account.services.auth_gateway import login_hash, mobile_logins, push_logins

GATEWAY = dict(
    AUTH_GATEWAY_URL='https://auth.test', AUTH_GATEWAY_API_KEY='key-1', AUTH_GATEWAY_LOGIN_SECRET='s3cret',
)


class FakeSession:
    def __init__(self):
        self.calls = []

    def put(self, url, json, headers, timeout):
        self.calls.append((url, json, headers))
        response = mock.Mock(status_code=200)
        response.json.return_value = {'logins': len(json['logins'])}
        return response


@override_settings(**GATEWAY)
class AuthGatewayPushTest(TestCase):
    def setUp(self):
        UserAccount.objects.create_user(username='Ivanov', password='x', role='staff')
        UserAccount.objects.create_user(username='blocked', password='x', role='staff', is_active=False)
        no_password = UserAccount.objects.create_user(username='nopass', role='staff')
        no_password.set_unusable_password()
        no_password.save()

    def test_hash_matches_gateway_formula(self):
        expected = hmac.new(b's3cret', b'ivanov', hashlib.sha256).hexdigest()
        self.assertEqual(login_hash(' Ivanov '), expected)

    def test_only_active_users_with_password(self):
        self.assertEqual(mobile_logins(), ['Ivanov'])

    def test_push_sends_hashes_not_logins(self):
        session = FakeSession()
        self.assertEqual(push_logins(session=session), 1)
        url, body, headers = session.calls[0]
        self.assertEqual(url, 'https://auth.test/api/backend/logins')
        self.assertEqual(headers['Authorization'], 'Bearer key-1')
        self.assertEqual(body['logins'], [login_hash('Ivanov')])
        self.assertNotIn('Ivanov', str(body))

    def test_user_change_schedules_push(self):
        with mock.patch('account.tasks.push_logins_to_gateway.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                UserAccount.objects.create_user(username='new_one', password='x', role='staff')
        delay.assert_called_once()

    @override_settings(AUTH_GATEWAY_URL='')
    def test_not_configured_does_nothing(self):
        self.assertEqual(push_logins(session=FakeSession()), 0)
