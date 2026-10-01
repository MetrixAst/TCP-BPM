# invoice_pdf_cache.py

Cache layer for the structured invoice payload (`InvoicePdfPayload`, see
`app/models/invoice_pdf_payload.py`) so a PDF can be re-rendered from a
previously-seen invoice without hitting live 1C every time.

## Flow

```
caller (nova_buh_1c_client.py / odata_1c_client.py: download_invoice_file)
  -> get_cached_payload(): hit -> render locally, 1C untouched
  -> miss/force -> live fetch cascade -> store_payload_if_valid()
```

## Functions

- `get_cached_payload(db, tenant, invoice_id)` — returns a ready-to-render
  payload with supplier requisites re-merged from the **current** `tenant`
  row, or `None` if there's no valid cache, or the cache is older than
  `LINE_ITEMS_FRESHNESS_TTL`. Callers must treat `None` the same as "no cache
  at all" — go fetch live.
- `store_payload_if_valid(db, tenant_id, invoice_id, payload, source=, tenant=)`
  — writes only if `is_valid_pdf_payload()` passes. Never delete-then-write:
  an invalid rehydrate leaves any existing valid row untouched.
- `is_valid_pdf_payload(payload)` — gate before caching. The live-fetch
  cascade has 5+ independent fallback attempts, any of which can silently
  return empty and fall through — fine for a one-off render, but caching that
  degradation would freeze it forever.
- `strip_tenant_sourced_fields(payload, tenant)` — decides which supplier
  requisite fields are safe to persist. Compares each field's value against
  what `_merge_supplier_requisites` would produce from a tenant-only fallback
  (no 1C data): equal → it's the tenant fallback, strip it (editing the bank
  account in the admin panel must apply immediately, not after cache
  expiry); different → it's real 1C data, keep it.
- `can_attempt_force_refresh` / `mark_force_refresh_attempted` — 5-minute
  cooldown (`FORCE_REFRESH_COOLDOWN`) per `(tenant_id, invoice_id)` so manual
  force-refresh can't itself reproduce the Nova 502 storm the cache exists to
  prevent.

## Constants

- `TENANT_SOURCED_KEYS` — fields that may come from `Tenant.invoice_*`
  fallback instead of 1C; never persisted unconditionally, see
  `strip_tenant_sourced_fields`.
- `LINE_ITEMS_FRESHNESS_TTL = 30min` — cached line items (qty/price/amount)
  expire and get refetched live. Added after a real bug (2026-09-14,
  Astranium invoice #00000003340): items had no TTL at all and froze forever
  after first fetch, even when 1C later recalculated the invoice (utility
  add-ons often post late). Not the same knob as `FORCE_REFRESH_COOLDOWN`
  (that throttles retry attempts, not staleness).
- `is_payload_cache_stale(db, tenant_id, invoice_id)` — tells apart "never
  cached" from "cached but stale" for callers (currently the Nova client)
  that also need to invalidate a downstream file-based PDF cache, whose mtime
  no longer reflects real 1C freshness once a payload-cache hit re-renders it.

## Gotchas

- Requisite fields have no per-field fallback in `invoice_report.py._pick_from_1c`
  for `supplier_iik/bik/bank_name/kbe` — the *only* place `Tenant.invoice_*`
  fallback enters the payload is `_merge_supplier_requisites` (called by
  `get_cached_payload` for both Nova and OData paths).
- `invoice_id` is GUID-validated (`_validate_invoice_id`, lazy-imported from
  `odata_1c_client._guid_literal`) before touching SQL.
