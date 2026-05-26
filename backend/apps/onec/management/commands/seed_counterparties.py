from django.core.management.base import BaseCommand

from onec.services.seed_counterparties import seed_demo_counterparties


class Command(BaseCommand):
    help = 'Загружает демо-контрагентов (DEMO-001 …) в справочник 1С'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Обновить демо-записи даже если в БД уже есть контрагенты',
        )

    def handle(self, *args, **options):
        result = seed_demo_counterparties(force=options['force'])
        status = result.get('status')
        if status == 'skipped':
            self.stdout.write(
                self.style.WARNING(result.get('reason', 'skipped')),
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Готово: создано {result.get("created")}, обновлено {result.get("updated")}, '
                    f'всего {result.get("total")}.',
                )
            )
