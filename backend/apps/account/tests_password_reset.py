from django.test import Client, TestCase
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
            role=RoleEnums.STAFF.value,
        )
        self.url = reverse('account:access_user_reset_password', args=[self.staff.pk])

    def test_staff_cannot_reset(self):
        self.client.login(username='pwd_staff', password='StaffOld1!')
        r = self.client.post(
            self.url,
            data='{"new_password1":"NewPass123!","new_password2":"NewPass123!"}',
            content_type='application/json',
        )
        self.assertIn(r.status_code, (403, 302))

    def test_admin_resets_password(self):
        self.client.login(username='pwd_admin', password='AdminOld1!')
        r = self.client.post(
            self.url,
            data='{"new_password1":"NewPass123!","new_password2":"NewPass123!"}',
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get('ok'))
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password('NewPass123!'))
        self.assertFalse(self.staff.check_password('StaffOld1!'))

    def test_mismatch_rejected(self):
        self.client.login(username='pwd_admin', password='AdminOld1!')
        r = self.client.post(
            self.url,
            data='{"new_password1":"NewPass123!","new_password2":"OtherPass1!"}',
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 400)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password('StaffOld1!'))
