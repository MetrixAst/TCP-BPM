#!/usr/bin/env python3
"""Одноразовый backfill: телефоны из counterparty_phones → 1С (OData City Mall).

Не удаляет данные. Только POST/PATCH в регистр контактной информации.

Без доступа к поду используйте admin API:
  POST /api/admin/trcs/{trc_id}/counterparty-phones/sync-to-1c?tenant_id=...&dry_run=true

Примеры CLI (если есть shell на сервере):
  cd backend
  APP_ENV_FILE=.env ../.venv/bin/python scripts/backfill_counterparty_phones_to_1c.py --tenant-id 1 --dry-run
  APP_ENV_FILE=.env ../.venv/bin/python scripts/backfill_counterparty_phones_to_1c.py --tenant-id 1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=int, required=True, help="ID арендатора (City Mall)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать, что будет отправлено (без записи в 1С)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Ограничить число контрагентов (0 = все)",
    )
    args = parser.parse_args()

    from app.db.database import SessionLocal
    from app.services.counterparty_phone_backfill import backfill_counterparty_phones_to_1c

    db = SessionLocal()
    try:
        result = backfill_counterparty_phones_to_1c(
            db,
            tenant_id=args.tenant_id,
            dry_run=args.dry_run,
            limit=args.limit,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        if result.get("error") and not result.get("ok"):
            return 1
        if result.get("fail_count"):
            return 2
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
