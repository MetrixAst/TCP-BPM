from django.core.management.base import BaseCommand

from django.db.models import Q
from django.utils import timezone

from account.models import Notification
from documents.models import Document


class Command(BaseCommand):
    help = 'Document remind'

    def handle(self, *args, **options):

        # document = Document.objects.first()
        # Notification.create_document_reminder(document)
        now = timezone.now()
        target_date = now + timezone.timedelta(days=3)
        notify_date = now - timezone.timedelta(days=1)
        document_qs = Document.objects.filter(end_date__lte=target_date).filter(Q(date_notify=None) | Q(date_notify__lt=notify_date))

        if document_qs.count() > 0:
            document = document_qs.first()
            document.date_notify = now
            document.save()

            Notification.create_document_reminder(document)