from django.core.management.base import BaseCommand
from django.conf import settings

from onec.client_1c import Client1C


class Command(BaseCommand):
    help = 'Retrieve data from 1C'

    def handle(self, *args, **options):
        client = Client1C(
            base_url=settings.ONE_C_BASE_URL,
            basic_auth_user=settings.ONE_C_BASIC_AUTH_USER,
            basic_auth_password=settings.ONE_C_BASIC_AUTH_PASSWORD,
            api_user=settings.ONE_C_API_USER,
            api_password=settings.ONE_C_API_PASSWORD,
        )
        try:
            client.authenticate()
            self.stdout.write(self.style.SUCCESS('Authenticated with 1C'))

            counterparties = client.get_counterparties(limit=100)
            self.stdout.write(self.style.SUCCESS(f'Retrieved {len(counterparties)} counterparties'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {e}'))
        finally:
            client.close()