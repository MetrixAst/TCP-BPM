"""Проверка SMTP: python manage.py send_test_email you@example.com"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Отправляет тестовое письмо через настроенный SMTP (Outlook / M365)'

    def add_arguments(self, parser):
        parser.add_argument('to', help='Email получателя')
        parser.add_argument(
            '--subject',
            default='metriX BPM — тест SMTP',
            help='Тема письма',
        )

    def handle(self, *args, **options):
        to = options['to'].strip()
        if '@' not in to:
            raise CommandError('Укажите корректный email получателя')

        backend = settings.EMAIL_BACKEND
        host = settings.EMAIL_HOST
        user = settings.EMAIL_HOST_USER or '(пусто)'
        self.stdout.write(f'Backend: {backend}')
        self.stdout.write(f'Host:    {host}:{settings.EMAIL_PORT} TLS={settings.EMAIL_USE_TLS}')
        self.stdout.write(f'From:    {settings.DEFAULT_FROM_EMAIL} (user={user})')
        self.stdout.write(f'To:      {to}')

        if not settings.EMAIL_HOST_PASSWORD and 'smtp' in backend:
            self.stdout.write(self.style.WARNING(
                'EMAIL_HOST_PASSWORD пустой — SMTP, скорее всего, отклонит отправку.'
            ))

        try:
            sent = send_mail(
                subject=options['subject'],
                message=(
                    'Это тестовое письмо из metriX BPM.\n'
                    'Если вы его получили — SMTP Outlook настроен корректно.\n'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(f'Ошибка отправки: {exc}') from exc

        if sent:
            self.stdout.write(self.style.SUCCESS('Письмо отправлено.'))
        else:
            raise CommandError('send_mail вернул 0 — письмо не отправлено.')
