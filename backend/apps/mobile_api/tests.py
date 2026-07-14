from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import PushToken, UserAccount

import io

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import UserAccount, Department, Employee
from hr.models import AttendanceRecord
from hr.enums import CheckInEnum



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

def _make_test_image():
    """Генерирует минимальное валидное JPEG-изображение в памяти для теста."""
    buffer = io.BytesIO()
    image = Image.new('RGB', (10, 10), color='red')
    image.save(buffer, format='JPEG')
    buffer.seek(0)
    return SimpleUploadedFile('test_photo.jpg', buffer.read(), content_type='image/jpeg')


class AttendanceCheckinApiTests(APITestCase):
    def setUp(self):
        self.department = Department.objects.create(name='Тестовый отдел')
        self.user = UserAccount.objects.create_user(
            username='checkin_user',
            password='testpass123',
            role='staff',
        )
        self.employee = Employee.objects.create(
            user=self.user,
            department=self.department,
        )
        self.client.force_authenticate(user=self.user)
        self.checkin_url = reverse('mobile_api:attendance-checkin')
        self.today_url = reverse('mobile_api:attendance-today')

    def test_checkin_with_photo_and_geo_returns_201(self):
        response = self.client.post(
            self.checkin_url,
            {
                'event_type': CheckInEnum.DAY_START.value,
                'photo': _make_test_image(),
                'latitude': '43.2380000',
                'longitude': '76.9450000',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        record = AttendanceRecord.objects.get(employee=self.employee)
        self.assertEqual(record.event_type, CheckInEnum.DAY_START.value)
        self.assertTrue(record.photo)
        self.assertIsNotNone(record.latitude)
        self.assertIsNotNone(record.longitude)

    def test_checkin_without_geo_still_succeeds(self):
        response = self.client.post(
            self.checkin_url,
            {
                'event_type': CheckInEnum.DAY_START.value,
                'photo': _make_test_image(),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_duplicate_checkin_same_type_same_day_rejected(self):
        # Первый чек-ин — успешен
        response1 = self.client.post(
            self.checkin_url,
            {
                'event_type': CheckInEnum.DAY_START.value,
                'photo': _make_test_image(),
            },
            format='multipart',
        )
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # Повторный чек-ин того же типа в тот же день — должен быть отклонён
        response2 = self.client.post(
            self.checkin_url,
            {
                'event_type': CheckInEnum.DAY_START.value,
                'photo': _make_test_image(),
            },
            format='multipart',
        )
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)

        # В базе только одна запись этого типа за сегодня
        count = AttendanceRecord.objects.filter(
            employee=self.employee,
            event_type=CheckInEnum.DAY_START.value,
        ).count()
        self.assertEqual(count, 1)

    def test_checkin_without_employee_profile_returns_403(self):
        guest_user = UserAccount.objects.create_user(
            username='guest_no_employee',
            password='testpass123',
            role='guest',
        )
        self.client.force_authenticate(user=guest_user)

        response = self.client.post(
            self.checkin_url,
            {
                'event_type': CheckInEnum.DAY_START.value,
                'photo': _make_test_image(),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_checkin_without_auth_returns_401(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self.checkin_url,
            {
                'event_type': CheckInEnum.DAY_START.value,
                'photo': _make_test_image(),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_today_endpoint_returns_marks(self):
        self.client.post(
            self.checkin_url,
            {
                'event_type': CheckInEnum.DAY_START.value,
                'photo': _make_test_image(),
            },
            format='multipart',
        )

        response = self.client.get(self.today_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['marks']), 1)
        self.assertEqual(response.data['marks'][0]['type'], CheckInEnum.DAY_START.value)

    def test_today_endpoint_empty_when_no_checkins(self):
        response = self.client.get(self.today_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['marks'], [])