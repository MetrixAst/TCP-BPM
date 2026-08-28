from django.core.management.base import BaseCommand
from hr.models import AttendanceManualReason

REASONS = [
    ('sick_leave', 'Больничный'),
    ('business_trip', 'Командировка'),
    ('valid_reason', 'Уважительная причина'),
    ('late_justified', 'Опоздание по уважительной причине'),
    ('early_leave_justified', 'Ранний уход по уважительной причине'),
    ('remote_work', 'Удалённая работа'),
    ('correction', 'Корректировка ошибки'),
    ('other', 'Другое'),
]


class Command(BaseCommand):
    help = 'Создаёт справочник оснований ручных отметок'

    def handle(self, *args, **options):
        created = 0
        for code, label in REASONS:
            _, was_created = AttendanceManualReason.objects.get_or_create(
                code=code,
                defaults={'label': label, 'is_active': True},
            )
            if was_created:
                created += 1
                self.stdout.write(f'  + {code}: {label}')
            else:
                self.stdout.write(f'  = {code}: уже существует')

        self.stdout.write(self.style.SUCCESS(f'\nГотово: создано {created} оснований'))
        