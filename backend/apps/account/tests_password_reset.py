from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from account.models import UserAccount
from account.role_permissions import RoleEnums


class AdminPasswordResetTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = UserAccount.objects.create_user(
            username='pwd_admin',
            password='AdminOld1!',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.staff = UserAccount.objects.create_user(
            username='pwd_staff',
            password='StaffOld1!',
            email='staff@example.com',
            role=RoleEnums.STAFF.value,
        )
        self.url = reverse('account:access_user_reset_password', args=[self.staff.pk])

    def test_staff_cannot_reset(self):
        self.client.login(username='pwd_staff', password='StaffOld1!')
        r = self.client.post(self.url, data='{}', content_type='application/json')
        self.assertIn(r.status_code, (403, 302))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_admin_reset_emails_password_without_showing_it(self):
        self.client.login(username='pwd_admin', password='AdminOld1!')
        r = self.client.post(self.url, data='{}', content_type='application/json')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get('ok'))
        self.assertNotIn('password', body)
        self.assertNotIn('Пароль:', body.get('detail', ''))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('pwd_staff', mail.outbox[0].body)
        self.assertIn('staff@example.com', mail.outbox[0].to)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.check_password('StaffOld1!'))
        sent_password = mail.outbox[0].body.split('Пароль: ', 1)[1].splitlines()[0]
        self.assertNotIn(sent_password, body.get('detail', ''))
        self.assertTrue(self.staff.check_password(sent_password))

    def test_missing_email_does_not_change_password(self):
        self.staff.email = ''
        self.staff.save(update_fields=['email'])
        self.client.login(username='pwd_admin', password='AdminOld1!')
        r = self.client.post(self.url, data='{}', content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password('StaffOld1!'))
