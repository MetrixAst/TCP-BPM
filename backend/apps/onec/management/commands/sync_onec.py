from django.core.management.base import BaseCommand

from onec.services.client_factory import is_onec_configured
from onec.services.sync_all import sync_all_from_1c
from onec.services.sync_cashflow import sync_cashflow_from_1c
from onec.services.sync_counterparties import sync_counterparties_from_1c
from onec.services.sync_data_queue import sync_data_queue_from_1c
from onec.services.sync_invoices import sync_generated_invoices_from_1c
from onec.services.sync_registry import sync_registry_from_1c


class Command(BaseCommand):
    help = 'Синхронизация данных из 1С в BPM (finances)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--only',
            choices=['all', 'counterparties', 'cashflow', 'registry', 'invoices', 'queue'],
            default='all',
        )

    def handle(self, *args, **options):
        if not is_onec_configured():
            self.stderr.write(self.style.ERROR(
                '1С не настроена: задайте ONE_C_BASE_URL, ONE_C_API_USER, ONE_C_API_PASSWORD в .env'
            ))
            return

        only = options['only']
        runners = {
            'counterparties': sync_counterparties_from_1c,
            'cashflow': sync_cashflow_from_1c,
            'registry': sync_registry_from_1c,
            'invoices': sync_generated_invoices_from_1c,
            'queue': sync_data_queue_from_1c,
            'all': sync_all_from_1c,
        }
        result = runners[only]()
        self.stdout.write(self.style.SUCCESS(str(result)))
