"""Сопоставление контрагента 1С с арендатором BPM."""

from __future__ import annotations

from django.db.models import Q

from onec.models import Counterparty
from tenants.models import Tenant


def resolve_tenant_for_counterparty(counterparty: Counterparty | None) -> Tenant | None:
    if not counterparty:
        return None

    via_invoice = Tenant.objects.filter(
        generated_invoices__counterparty_id=counterparty.pk,
    ).distinct().first()
    if via_invoice:
        return via_invoice

    name = (counterparty.short_name or counterparty.full_name or '').strip()
    if name:
        tenant = Tenant.objects.filter(name__iexact=name).first()
        if tenant:
            return tenant
        tenant = Tenant.objects.filter(name__icontains=name[:40]).first()
        if tenant:
            return tenant

    if counterparty.bin_number:
        tenant = Tenant.objects.filter(
            Q(phone__icontains=counterparty.bin_number)
            | Q(note__icontains=counterparty.bin_number),
        ).first()
        if tenant:
            return tenant

    return None


def resolve_tenant_by_id_1c(counterparty_id_1c: str) -> Tenant | None:
    if not counterparty_id_1c:
        return None
    cp = Counterparty.objects.filter(id_1c=counterparty_id_1c).first()
    return resolve_tenant_for_counterparty(cp)
