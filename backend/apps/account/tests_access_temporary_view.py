from django.test import TestCase

from account.models import UserAccount


def make_user(username, role='staff'):
    return UserAccount.objects.create_user(username=username, password='pass', role=role)


class AccessTemporaryViewTest(TestCase):
    """Право на страницу /account/access/temporary/ (сама выдача/отзыв — на стороне DRF, см. tests_temp_access.py)."""

    def setUp(self):
        self.admin = make_user('admin_ta_view', role='administrator')
        self.staff = make_user('staff_ta_view', role='staff')

    def test_admin_can_open_page(self):
        self.client.force_login(self.admin)
        response = self.client.get('/account/access/temporary')
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_open_page(self):
        self.client.force_login(self.staff)
        response = self.client.get('/account/access/temporary')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get('/account/access/temporary')
        self.assertEqual(response.status_code, 302)
