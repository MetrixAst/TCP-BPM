from celery import shared_task
from decouple import config
from pyfcm import FCMNotification

from project.utils import get_or_none

@shared_task
def send_notifications_task(notification_id):
    from account.models import Notification, NotificationIndicator, PushToken
    notification = get_or_none(Notification, id=notification_id)
    if notification is not None:
        users = notification.users.all()
        # Создаём индикаторы для бейджей независимо от того, настроен ли FCM —
        # это нужно и для веба, и для мобилки, даже если push не отправится.
        for user in users:
            NotificationIndicator.objects.get_or_create(
                user=user,
                target_id=notification.target_id,
                target_type=notification.target_type,
            )
        try:
            FCM_ACCOUNT = config('FCM_ACCOUNT')
            FCM_PROJECT_ID = config('FCM_PROJECT_ID')
        except Exception:
            # FCM не настроен в этом окружении — индикаторы уже созданы,
            # просто пропускаем отправку push.
            return

        push_tokens = PushToken.objects.filter(user__in=users)
        registration_ids = list(push_tokens.values_list('fcm', flat=True))
        registration_ids = list(dict.fromkeys(registration_ids))
        if len(registration_ids) > 0:
            data = {
                'notification_id': str(notification.id),
                'title': notification.title,
                'target_type': notification.target_type,
                'target_id': str(notification.target_id),
                'url': notification.url or '',
            }
            fcm = FCMNotification(service_account_file=FCM_ACCOUNT, project_id=FCM_PROJECT_ID)
            for current in registration_ids:
                try:
                    fcm.notify(fcm_token=current, notification_title=notification.title, notification_body=notification.text, data_payload=data)
                except:
                    pass