#!/usr/bin/env python3
"""Ручной запуск авторассылки (как scheduler, но сразу).

Запуск в pod invoice-api:

    python scripts/run_auto_notifications.py
    python scripts/run_auto_notifications.py --tenant-id 3
    python scripts/run_auto_notifications.py --force-window
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.database import SessionLocal
from app.services.auto_notification_service import AutoNotificationService, in_sending_window


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tenant-id",
        type=int,
        default=None,
        help="Только этот арендатор (например 3 = Maxi Mall)",
    )
    parser.add_argument(
        "--force-window",
        action="store_true",
        help="Отправлять даже вне окна 09:00–18:00 Астана",
    )
    args = parser.parse_args()

    can_send = True if args.force_window else in_sending_window()
    print(f"can_send={can_send} (force_window={args.force_window})")

    db = SessionLocal()
    try:
        svc = AutoNotificationService(db)
        if args.tenant_id:
            sent = svc.run_for_tenant(args.tenant_id, can_send=can_send)
            print(f"tenant_id={args.tenant_id} sent={sent}")
        elif args.force_window:
            sent = _run_all(db, can_send=True)
            print(f"sent_total={sent}")
        else:
            sent = svc.run_for_all_tenants()
            print(f"sent_total={sent}")
    finally:
        db.close()
    return 0


def _run_all(db, *, can_send: bool) -> int:
    from app.models.catalog import Tenant
    from app.services.tenant_1c import tenant_has_1c_credentials

    svc = AutoNotificationService(db)
    tenants = (
        db.query(Tenant)
        .filter(Tenant.is_active.is_(True))
        .filter(Tenant.green_api_id_instance.isnot(None))
        .filter(Tenant.green_api_api_token.isnot(None))
        .all()
    )
    total = 0
    for tenant in tenants:
        if not tenant_has_1c_credentials(tenant):
            continue
        try:
            total += svc.run_for_tenant(tenant.id, can_send=can_send)
        except Exception as exc:
            print(f"ERROR tenant={tenant.id}: {exc}", file=sys.stderr)
    return total


if __name__ == "__main__":
    raise SystemExit(main())
