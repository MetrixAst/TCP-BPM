"""Экран «Синхронизация с 1С»: состояние подключения, журнал загрузок, сопоставление арендаторов."""

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from account.role_permissions import PermissionEnums, need_permission
from .models import InvoiceSyncRun


@need_permission(PermissionEnums.FINANCE_INVOICES)
def sync_status(request):
    from onec.services.client_factory import is_onec_configured
    from tenants.models import Tenant
    from .services.invoice_service import is_configured

    runs = list(InvoiceSyncRun.objects.all()[:20])
    last = runs[0] if runs else None
    last_ok = InvoiceSyncRun.objects.exclude(status=InvoiceSyncRun.Status.FAILED).first()

    return render(request, 'site/finances/sync_status.html', {
        'invoice_service_configured': is_configured(),
        'invoice_service_url': getattr(settings, 'INVOICE_SERVICE_URL', ''),
        'onec_rest_configured': is_onec_configured(),
        'runs': runs,
        'last': last,
        'last_ok': last_ok,
        'unmatched': (last.unmatched if last else [])[:100],
        'tenants': Tenant.objects.filter(is_active=True, counterparty__isnull=True).order_by('name'),
        'sync_months': getattr(settings, 'INVOICE_SERVICE_SYNC_MONTHS', 3),
    })


@need_permission(PermissionEnums.FINANCE_INVOICES)
@require_POST
def sync_run(request):
    from .services.invoice_service import is_configured
    from .services.invoice_sync import sync_invoices_from_service

    if not is_configured():
        messages.error(request, 'Invoice-сервис не настроен: заполните INVOICE_SERVICE_* в .env.')
        return redirect('finances:sync_status')

    from .services.rent_plan import generate_rent_plan

    run = sync_invoices_from_service(trigger='manual')
    generate_rent_plan()
    if run.status == InvoiceSyncRun.Status.FAILED:
        messages.error(request, f'Загрузка не удалась: {run.error[:300]}')
    else:
        stats = run.stats
        messages.success(
            request,
            f"Загружено счетов: {stats.get('invoices', 0)}, в реестр: {stats.get('registry', 0)}, "
            f"не сопоставлено: {stats.get('unmatched', 0)}.",
        )
    return redirect('finances:sync_status')


@need_permission(PermissionEnums.FINANCE_INVOICES)
@require_POST
def link_counterparty(request):
    """Связать контрагента из 1С с арендатором BPM; следующая загрузка разнесёт его счета в реестр."""
    from onec.models import Counterparty
    from tenants.models import Tenant

    counterparty = Counterparty.objects.filter(id_1c=request.POST.get('onec_id')).first()
    tenant = get_object_or_404(Tenant, pk=request.POST.get('tenant'))
    if counterparty is None:
        messages.error(request, 'Контрагент не найден — запустите загрузку ещё раз.')
        return redirect('finances:sync_status')

    tenant.counterparty = counterparty
    tenant.save(update_fields=['counterparty'])
    messages.success(
        request,
        f'«{counterparty.short_name}» связан с арендатором «{tenant.name}». '
        'Счета попадут в реестр при следующей загрузке.',
    )
    return redirect('finances:sync_status')
