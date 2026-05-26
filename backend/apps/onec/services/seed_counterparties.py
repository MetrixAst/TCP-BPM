"""Загрузка демо-контрагентов в БД."""

from __future__ import annotations

from django.utils import timezone

from onec.demo_counterparties import DEMO_COUNTERPARTIES
from onec.models import Counterparty


def seed_demo_counterparties(*, force: bool = False) -> dict:
    """
    Создаёт или обновляет демо-контрагентов (id_1c DEMO-*).
    Новые записи из списка добавляются даже если в БД уже есть другие контрагенты.
    """
    if force:
        Counterparty.objects.filter(id_1c__startswith='DEMO-').delete()

    now = timezone.now()
    created = updated = 0

    for row in DEMO_COUNTERPARTIES:
        id_1c = row['id_1c']
        defaults = {**row, 'synced_at': now}
        defaults.pop('id_1c')
        _, was_created = Counterparty.objects.update_or_create(
            id_1c=id_1c,
            defaults=defaults,
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return {
        'status': 'ok',
        'created': created,
        'updated': updated,
        'total': Counterparty.objects.count(),
    }
