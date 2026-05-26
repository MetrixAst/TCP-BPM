"""Синхронизация контрагентов onec.Counterparty → purchases.Supplier."""

from purchases.enums import SupplierStatusEnum, SupplierTypeEnum
from purchases.models import Supplier


def _safe_email(value):
    email = (value or '').strip()
    if not email or '@' not in email:
        return None
    return email[:40]


def sync_counterparties_to_suppliers():
    """
    Создаёт или обновляет записи Supplier по данным из 1С.
    Возвращает число обработанных контрагентов.
    """
    try:
        from onec.models import Counterparty
    except ImportError:
        return 0

    count = 0
    for cp in Counterparty.objects.all().order_by('short_name'):
        name = (cp.short_name or cp.full_name or cp.id_1c)[:100]
        address = ((cp.address or '').strip()[:60]) or 'г. Алматы'
        bin_id = (cp.bin_number or cp.iin or '').strip() or None

        Supplier.objects.update_or_create(
            onec_id=cp.id_1c,
            defaults={
                'name': name,
                'identifier': bin_id,
                'status': SupplierStatusEnum.CHECKED.value[0],
                'supplier_type': (
                    SupplierTypeEnum.LEGAL.value[0]
                    if cp.is_supplier
                    else SupplierTypeEnum.INDIVIDUAL.value[0]
                ),
                'address1': address if cp.address else None,
                'address2': address,
                'phone': (cp.phone or '')[:40] or None,
                'email': _safe_email(cp.email),
                'contacts': f'1С · {cp.id_1c}'[:100],
            },
        )
        count += 1

    return count
