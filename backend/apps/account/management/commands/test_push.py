from django.core.management.base import BaseCommand
from account.tasks import send_notifications_task


class Command(BaseCommand):
    help = 'Supplier remind'

    def handle(self, *args, **options):
        send_notifications_task(87)