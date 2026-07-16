from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import PushToken, UserAccount, Notification, NotificationIndicator

import io

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import UserAccount, Department, Employee
from hr.models import AttendanceRecord
from hr.enums import CheckInEnum
from tickets.models import ServiceRequest, TicketMessage
from tenants.models import Tenant


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

class TicketsApiTests(APITestCase):
    def setUp(self):
        self.department = Department.objects.create(name='Тестовый отдел для тикетов')

        # Внутренний сотрудник (менеджер) — видит все заявки
        self.manager_user = UserAccount.objects.create_user(
            username='manager_tickets',
            password='testpass123',
            role='administrator',
        )

        # Арендатор — видит только свои заявки
        self.tenant = Tenant.objects.create(
            name='Тестовый арендатор',
            area=50.0,
            price=1000.0,
            phone='+77001234567',
            email='tenant@test.kz',
            address='ул. Тестовая, 1',
            contact='Иван Иванов',
        )
        self.tenant_user = UserAccount.objects.create_user(
            username='tenant_tickets',
            password='testpass123',
            role='tenant',
            tenant=self.tenant,
        )

        self.list_url = reverse('mobile_api:tickets-list-create')

    def test_list_requires_auth(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_ticket_with_photo_returns_201(self):
        self.client.force_authenticate(user=self.manager_user)

        response = self.client.post(
            self.list_url,
            {
                'title': 'Сломан кондиционер',
                'description': 'Не охлаждает, дует тёплым воздухом',
                'category': 'hvac',
                'priority': 'high',
                'room': '305',
                'photo': _make_test_image(),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ServiceRequest.objects.count(), 1)
        ticket = ServiceRequest.objects.first()
        self.assertEqual(ticket.title, 'Сломан кондиционер')
        self.assertEqual(ticket.category, 'hvac')
        self.assertTrue(ticket.photo)

    def test_create_ticket_without_photo_succeeds(self):
        self.client.force_authenticate(user=self.manager_user)

        response = self.client.post(
            self.list_url,
            {
                'title': 'Нужна уборка',
                'description': 'Пролили кофе на ковёр',
                'category': 'cleaning',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_ticket_missing_required_field_returns_400(self):
        self.client.force_authenticate(user=self.manager_user)

        response = self.client.post(
            self.list_url,
            {'description': 'Без темы'},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_filters_by_status(self):
        self.client.force_authenticate(user=self.manager_user)

        ServiceRequest.objects.create(
            author=self.manager_user, title='Новая заявка',
            description='...', category='other', status='new',
        )
        ServiceRequest.objects.create(
            author=self.manager_user, title='Заявка в работе',
            description='...', category='other', status='in_progress',
        )

        response = self.client.get(self.list_url, {'status': 'new'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['status'], 'new')

    def test_list_filters_by_category(self):
        self.client.force_authenticate(user=self.manager_user)

        ServiceRequest.objects.create(
            author=self.manager_user, title='Электрика',
            description='...', category='electrical',
        )
        ServiceRequest.objects.create(
            author=self.manager_user, title='Сантехника',
            description='...', category='plumbing',
        )

        response = self.client.get(self.list_url, {'category': 'electrical'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['category'], 'electrical')

    def test_list_is_paginated(self):
        self.client.force_authenticate(user=self.manager_user)

        for i in range(25):
            ServiceRequest.objects.create(
                author=self.manager_user, title=f'Заявка {i}',
                description='...', category='other',
            )

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertIn('count', response.data)
        self.assertEqual(response.data['count'], 25)
        self.assertEqual(len(response.data['results']), 20)  # page_size

    def test_tenant_sees_only_own_tickets(self):
        # Заявка от менеджера
        ServiceRequest.objects.create(
            author=self.manager_user, title='Заявка менеджера',
            description='...', category='other',
        )
        # Заявка от арендатора
        ServiceRequest.objects.create(
            author=self.tenant_user, tenant=self.tenant, title='Заявка арендатора',
            description='...', category='other',
        )

        self.client.force_authenticate(user=self.tenant_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Заявка арендатора')

    def test_manager_sees_all_tickets(self):
        ServiceRequest.objects.create(
            author=self.manager_user, title='Заявка менеджера',
            description='...', category='other',
        )
        ServiceRequest.objects.create(
            author=self.tenant_user, tenant=self.tenant, title='Заявка арендатора',
            description='...', category='other',
        )

        self.client.force_authenticate(user=self.manager_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_detail_returns_full_ticket_info(self):
        self.client.force_authenticate(user=self.manager_user)
        ticket = ServiceRequest.objects.create(
            author=self.manager_user, title='Детальная заявка',
            description='Полное описание проблемы', category='it',
        )

        detail_url = reverse('mobile_api:tickets-detail', args=[ticket.id])
        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Детальная заявка')
        self.assertEqual(response.data['description'], 'Полное описание проблемы')
        self.assertIn('attachments', response.data)

    def test_detail_not_found_returns_404(self):
        self.client.force_authenticate(user=self.manager_user)

        detail_url = reverse('mobile_api:tickets-detail', args=[99999])
        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_tenant_cannot_see_others_ticket_detail(self):
        other_tenant = Tenant.objects.create(
            name='Другой арендатор',
            area=50.0,
            price=1000.0,
            phone='+77009876543',
            email='other_tenant@test.kz',
            address='ул. Другая, 2',
            contact='Пётр Петров',
        )
        other_ticket = ServiceRequest.objects.create(
            author=self.manager_user, tenant=other_tenant, title='Чужая заявка',
            description='...', category='other',
        )

        self.client.force_authenticate(user=self.tenant_user)
        detail_url = reverse('mobile_api:tickets-detail', args=[other_ticket.id])
        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class TicketMessagesApiTests(APITestCase):
    def setUp(self):
        self.manager_user = UserAccount.objects.create_user(
            username='manager_chat',
            password='testpass123',
            role='administrator',
        )

        self.tenant = Tenant.objects.create(
            name='Арендатор для чата',
            area=50.0,
            price=1000.0,
            phone='+77001112233',
            email='chat_tenant@test.kz',
            address='ул. Чатовая, 3',
            contact='Сергей Сергеев',
        )
        self.tenant_user = UserAccount.objects.create_user(
            username='tenant_chat',
            password='testpass123',
            role='tenant',
            tenant=self.tenant,
        )

        self.stranger_user = UserAccount.objects.create_user(
            username='stranger_chat',
            password='testpass123',
            role='tenant',
        )

        self.ticket = ServiceRequest.objects.create(
            author=self.tenant_user,
            tenant=self.tenant,
            title='Заявка с чатом',
            description='Описание проблемы',
            category='other',
        )

        self.messages_url = reverse('mobile_api:tickets-messages', args=[self.ticket.id])

    def test_messages_require_auth(self):
        response = self.client.get(self.messages_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_author_can_view_empty_chat(self):
        self.client.force_authenticate(user=self.tenant_user)
        response = self.client.get(self.messages_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'], [])

    def test_author_can_send_message(self):
        self.client.force_authenticate(user=self.tenant_user)

        response = self.client.post(
            self.messages_url,
            {'text': 'У меня проблема с кондиционером'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TicketMessage.objects.filter(request=self.ticket).count(), 1)
        message = TicketMessage.objects.first()
        self.assertEqual(message.text, 'У меня проблема с кондиционером')
        self.assertEqual(message.author, self.tenant_user)

    def test_manager_can_view_and_reply(self):
        self.client.force_authenticate(user=self.tenant_user)
        self.client.post(self.messages_url, {'text': 'Вопрос от арендатора'}, format='json')

        self.client.force_authenticate(user=self.manager_user)
        response = self.client.post(
            self.messages_url,
            {'text': 'Ответ от менеджера'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        list_response = self.client.get(self.messages_url)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data['results']), 2)

    def test_stranger_cannot_view_chat(self):
        self.client.force_authenticate(user=self.stranger_user)
        response = self.client.get(self.messages_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_stranger_cannot_send_message(self):
        self.client.force_authenticate(user=self.stranger_user)

        response = self.client.post(
            self.messages_url,
            {'text': 'Попытка чужого сообщения'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(TicketMessage.objects.count(), 0)

    def test_assignee_can_view_chat(self):
        self.ticket.assignee = self.manager_user
        self.ticket.save(update_fields=['assignee'])

        assignee_user = UserAccount.objects.create_user(
            username='assignee_chat',
            password='testpass123',
            role='staff',
        )
        self.ticket.assignee = assignee_user
        self.ticket.save(update_fields=['assignee'])

        self.client.force_authenticate(user=assignee_user)
        response = self.client.get(self.messages_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_send_message_missing_text_returns_400(self):
        self.client.force_authenticate(user=self.tenant_user)

        response = self.client.post(self.messages_url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_messages_ordered_chronologically(self):
        self.client.force_authenticate(user=self.tenant_user)
        self.client.post(self.messages_url, {'text': 'Первое сообщение'}, format='json')
        self.client.post(self.messages_url, {'text': 'Второе сообщение'}, format='json')

        response = self.client.get(self.messages_url)

        results = response.data['results']
        self.assertEqual(results[0]['text'], 'Первое сообщение')
        self.assertEqual(results[1]['text'], 'Второе сообщение')

    def test_messages_for_nonexistent_ticket_returns_404(self):
        self.client.force_authenticate(user=self.manager_user)

        bad_url = reverse('mobile_api:tickets-messages', args=[99999])
        response = self.client.get(bad_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class NotificationsApiTests(APITestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            username='notif_user',
            password='testpass123',
            role='staff',
        )
        self.other_user = UserAccount.objects.create_user(
            username='notif_other',
            password='testpass123',
            role='staff',
        )

        self.list_url = reverse('mobile_api:notifications-list')

    def test_list_requires_auth(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_returns_only_own_notifications(self):
        notif1 = Notification.objects.create(title='Моё уведомление', text='Текст 1')
        notif1.users.add(self.user)

        notif2 = Notification.objects.create(title='Чужое уведомление', text='Текст 2')
        notif2.users.add(self.other_user)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Моё уведомление')

    def test_notification_unread_by_default_when_indicator_exists(self):
        notif = Notification.objects.create(
            title='Задача назначена', text='...',
            target_type='task', target_id=42,
        )
        notif.users.add(self.user)
        NotificationIndicator.objects.create(
            user=self.user, target_type='task', target_id=42,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)

        results = response.data['results']
        self.assertEqual(results[0]['is_read'], False)

    def test_notification_read_when_no_indicator(self):
        notif = Notification.objects.create(
            title='Старое уведомление', text='...',
            target_type='task', target_id=99,
        )
        notif.users.add(self.user)
        # индикатора нет -> уже прочитано (или прочитали ранее)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)

        results = response.data['results']
        self.assertEqual(results[0]['is_read'], True)

    def test_mark_as_read_removes_indicator(self):
        notif = Notification.objects.create(
            title='Отметить прочитанным', text='...',
            target_type='task', target_id=7,
        )
        notif.users.add(self.user)
        NotificationIndicator.objects.create(
            user=self.user, target_type='task', target_id=7,
        )

        self.client.force_authenticate(user=self.user)
        read_url = reverse('mobile_api:notifications-read', args=[notif.id])
        response = self.client.post(read_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            NotificationIndicator.objects.filter(
                user=self.user, target_type='task', target_id=7
            ).exists()
        )

    def test_mark_as_read_for_nonexistent_notification_returns_404(self):
        self.client.force_authenticate(user=self.user)
        read_url = reverse('mobile_api:notifications-read', args=[99999])
        response = self.client.post(read_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_mark_others_notification_as_read(self):
        notif = Notification.objects.create(title='Чужое', text='...')
        notif.users.add(self.other_user)

        self.client.force_authenticate(user=self.user)
        read_url = reverse('mobile_api:notifications-read', args=[notif.id])
        response = self.client.post(read_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_data_payload_includes_notification_id_target_and_url(self):
        from unittest.mock import patch

        notif = Notification.objects.create(
            title='Push тест', text='Текст пуша',
            target_type='task', target_id=15,
        )
        notif.users.add(self.user)

        with patch('account.tasks.config') as mock_config, \
             patch('account.tasks.FCMNotification') as mock_fcm_class, \
             patch('account.models.PushToken.objects.filter') as mock_filter:
            mock_config.side_effect = lambda key: f'fake-{key}'
            mock_filter.return_value.values_list.return_value = ['fake-token']
            mock_fcm_instance = mock_fcm_class.return_value

            from account.tasks import send_notifications_task
            send_notifications_task(notif.id)

            call_kwargs = mock_fcm_instance.notify.call_args.kwargs
            data_payload = call_kwargs['data_payload']

            self.assertEqual(data_payload['notification_id'], str(notif.id))
            self.assertEqual(data_payload['target_type'], 'task')
            self.assertEqual(data_payload['target_id'], '15')
            self.assertIn('url', data_payload)