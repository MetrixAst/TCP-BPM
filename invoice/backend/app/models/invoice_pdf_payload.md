# invoice_pdf_payload.py

SQLAlchemy model `InvoicePdfPayload` — table `invoice_pdf_payloads`. Caches the
*structured* invoice data (number, date, line items, amount…) used to render a
PDF, not PDF bytes. Read/written by `invoice_pdf_cache.py`.

## Key columns

- PK is `(tenant_id, invoice_id)` — `invoice_id` alone isn't unique across 1C
  orgs, so `tenant_id` has to be part of the key, not just an index.
- `payload` is `JSON` (not Postgres `JSONB`): rows are always read whole by PK,
  never filtered by payload content, so portability wins over indexability —
  and it lets the service be tested against in-memory SQLite instead of
  mocking every call.
- `payload IS NULL` doesn't mean "cached empty" — it means the row exists only
  to throttle force-refresh attempts (see `last_force_refresh_attempt_at`).
  An invoice that never passed the validity gate would otherwise never get a
  row at all, and there'd be nothing to throttle against.
- `source`: `"nova"` or `"odata"`, `NULL` while `payload` is `NULL`.
- `last_force_refresh_attempt_at`: tracks the last *attempt* (success or
  failure), separate from `fetched_at` — a failed attempt shouldn't grant an
  immediate retry that hammers Nova again.
- Supplier requisites (IIK/BIK/KBe/bank/address/KNP/contract) are deliberately
  **not** cached here — they're re-merged from the live `Tenant` row on every
  read. See `invoice_pdf_cache.py` for why caching them is a "wrong bank
  account" risk.

No behavior lives in this file — see `invoice_pdf_cache.py` for read/write
logic and staleness rules.
