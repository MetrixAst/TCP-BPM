from django.core.management.base import BaseCommand
from django.conf import settings

from esigner.client import ESignerClient


class Command(BaseCommand):
    help = "Создаёт папку eSigner и настраивает callback URL (запускать один раз)"

    def add_arguments(self, parser):
        parser.add_argument("--callback-url", required=True)

    def handle(self, *args, **options):
        client = ESignerClient()
        folder_id = client.ensure_folder("Мои договоры", settings.ESIGNER_COMPANY_ID)
        client.set_callback_url(settings.ESIGNER_COMPANY_ID, options["callback_url"])
        self.stdout.write(self.style.SUCCESS(f"folder_id={folder_id} - впишите его в ESIGNER_FOLDER_ID"))