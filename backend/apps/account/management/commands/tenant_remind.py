from django.core.management.base import BaseCommand

from django.db.models import Q
from django.utils import timezone

from account.models import Notification
from tenants.models import Tenant


class Command(BaseCommand):
    help = 'Supplier remind'

    def handle(self, *args, **options):

        now = timezone.now()
        target_date = now + timezone.timedelta(days=90)
        notify_date = now - timezone.timedelta(days=20)

        tenant_qs = Tenant.objects.filter(end_date__lte=target_date).filter(Q(date_notify=None) | Q(date_notify__lt=notify_date))

        if tenant_qs.count() > 0:
            tenant = tenant_qs.first()
            tenant.date_notify = now
            tenant.save()

            Notification.create_tenant_notify(tenant)