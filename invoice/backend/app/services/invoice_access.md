# invoice_access.py

Access control: verifies an invoice and its cached PDF belong to a specific
counterparty, and that WhatsApp sends only go to that counterparty's own
phone number. Also resolves service-type-by-line-items via live 1C and finds
invoice IDs by counterparty/service type.

## Ownership checks

- `find_cached_invoice_pdf(invoice_id, db=, tenant_id=)` — locates a cached
  PDF under `downloads/`. When `db`+`tenant_id` are given, first confirms via
  `TenantPayment` (FK) that this `invoice_id` actually belongs to that
  tenant, before returning any path — Nova/COM `invoice_id` is **not**
  globally unique across 1C orgs, so a bare filename lookup could previously
  hand one tenant another tenant's cached PDF (their bank details, their
  counterparty name). Only returns a path if
  `_cached_pdf_meta_has_supplier_banks` confirms the sidecar `.meta.json` has
  real bank fields.
- `invoice_belongs_to_counterparty_in_db(db, invoice_id, counterparty_id,
  tenant_id=)` — same check against already-synced `TenantPayment` rows, no
  live 1C. Filters by `tenant_id` (FK), not name matching.
- `assert_invoice_belongs_to_counterparty(integration, invoice_id,
  counterparty_id)` — live-1C version, raises `HTTPException` (404 if the
  invoice doesn't exist in 1C, 403 if it belongs to someone else).
- `resolve_invoice_for_counterparty(...)` — the main entry point combining
  the above: given some mix of `invoice_id`/`counterparty_id`, resolves both
  and enforces ownership. `skip_live_1c=True` uses only the DB check.

## Phone allow-list

- `assert_phone_allowed_for_counterparty(db, tenant_id, counterparty_id,
  phone_number, integration=)` — the number must match a phone known for
  that counterparty, from either the admin panel (`CounterpartyPhone`) or
  live 1C (`get_1c_phones_for_counterparty`). If neither source has any
  phone on file, any submitted number is allowed (manual entry from the UI
  table).
- `collect_allowed_phones` / `get_allowed_phones` — union of admin-panel and
  1C phones for a counterparty.

## Service-type / invoice lookup

- `invoice_service_types_from_1c(client, invoice, tenant=)` — line-item-based
  service types, always fetched live (`client.fetch_invoice_line_items`)
  since the OData invoice list doesn't include line items.
- `find_invoice_id_for_service_type(integration, counterparty_id,
  service_type, since=, tenant=)` — most recent invoice of a counterparty
  matching a given service type, scanning live invoices newest-first.
- `find_latest_invoice_id(integration, counterparty_id, since=)` — most
  recent invoice of a counterparty, any type.

`_raise_if_nova_unavailable` converts a `Nova1CServiceError` into a 503 with a
hint to check `NOVA_ADMIN_EMAIL`/`NOVA_ADMIN_PASSWORD` secrets — used by both
lookup functions above.
