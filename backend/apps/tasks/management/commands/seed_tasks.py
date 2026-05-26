from django.core.management.base import BaseCommand

from tasks.services.seed_tasks import seed_demo_tasks


class Command(BaseCommand):
    help = 'Создаёт демо-задачи для менеджера задач и дашборда'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Пересоздать демо-задачи с теми же названиями',
        )

    def handle(self, *args, **options):
        result = seed_demo_tasks(force=options['force'])
        status = result.get('status')
        if status == 'skipped':
            self.stdout.write(
                self.style.WARNING(
                    f'Демо-задачи уже есть (всего задач: {result.get("count")}). '
                    'Запустите с --force для пересоздания.',
                )
            )
        elif status == 'error':
            self.stdout.write(self.style.ERROR(result.get('error', 'unknown')))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Создано задач: {result.get("created")}, всего в БД: {result.get("total")}.',
                )
            )
