# invoice_service_type.py

Classifies an invoice by its line-item names into one or more
`ServiceType`s: `rent`, `utilities`, `operations` (formerly "эксплуатация"),
`signage`, `assp` — matched via keyword substrings, global/same for every
tenant (per-tenant keyword overrides exist in the schema but are disabled in
`app/api/admin.py`). Plus `debt`/`other`, which 1C line items never produce —
those are set explicitly by the xlsx importer (`app/services/xlsx_import/`).

## Core functions

- `resolve_invoice_service_types(items, keywords=)` — returns all matching
  types found across an invoice's line items, ordered by `SERVICE_TYPE_ORDER`
  (frequency/importance, not alphabetical). One invoice can be both rent and
  utilities.
- `resolve_invoice_service_type(...)` — singular convenience wrapper, returns
  the first type or `"unknown"`.
- `format_service_types_label(types)` / `parse_stored_service_types(raw)` —
  serialize to/from the comma-joined string stored in
  `TenantPayment.service_type` (e.g. `"rent,utilities"`, `"unknown"`). One
  invoice with multiple types is one registry row, not split rows.
  `parse_stored_service_types` is the fast path that avoids a live 1C call
  when the type was already computed and saved by `sync_from_1c` — added
  2026-09-02 after bulk debtor notify (230+ invoices) timed out hitting 1C
  per-invoice for a value already on disk.
- `tenant_due_day_for_service` / `due_day_for_service_type` /
  `due_date_in_invoice_month` — due-day resolution per service type, and the
  "due date must be strictly after the invoice date" rule (rolls to next
  month if the invoice was issued after this month's due day already passed
  — see the docstring on `due_date_in_invoice_month` for the exact bug this
  fixed).

## Keywords

`DEFAULT_PAYMENT_KEYWORDS` (a `PaymentKeywords` dataclass): rent=`аренд`,
utilities=`коммун|электр|вода|тепл|тбо|мусор|канал|интернет`,
operations=`эксплуат|маркетинг`, signage=`вывеск`, assp=`ассп` (confirmed
against real ИП Ибрагимов/CityMall invoices, 2026-08-20 — note real spelling
is "АССП" with two С's, not "АСПП").

`DEFAULT_KNP_BY_SERVICE_TYPE` — fallback КНП code per service type when
neither the 1C document nor `Tenant.invoice_payment_knp` has one:
`rent`/`operations` → `855`, `utilities` → `856` (operations was `858` until
2026-09-02, changed to match rent per a Maxi Mall manager request).
`signage`/`assp`/`debt`/`other`/`unknown` still use the tenant's single
fallback KNP.

`debt`/`other` were added 2026-08-26 for the Maxi Mall xlsx importer
("Долг пред.периода"/"Прочее" columns) and are deliberately *not* mapped onto
`rent`/`operations` — a prior-period debt line isn't always rent, and folding
it into operations would route reminders to the wrong contact.
