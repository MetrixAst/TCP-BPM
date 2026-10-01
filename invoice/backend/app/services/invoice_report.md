# invoice_report.py

Renders the formal "Счёт на оплату" PDF pixel-matched to a reference layout
(`app/assets/reference_invoice_18490.pdf`, from a real client sample). This is
the invoice PDF actually sent to tenants — payment details table, item table,
totals in words, executor signature/stamp. `invoice_pdf.py` is only the
unstyled fallback.

## Entry point

- `generate_formal_invoice_document(invoice, save_path, tenant)` — resolves a
  render-tenant (real `Tenant`, or a synthesized `SimpleNamespace` built from
  `invoice` data when `tenant` is `None`, via `_resolve_render_tenant`),
  builds the PDF via `_render_reference_invoice_pdf`, returns the output path
  or `None` on failure (logs the exception, doesn't raise).

## Layout

All X/Y coordinates are measured from the reference PDF in points and
converted to mm (`_pt_mm`, `X_*`/`Y_*` constants). The payment-details table
(`Образец платежного поручения`) and everything below it use a `layout_shift`
closure (`yp()`) so a taller-than-reference table (e.g. a long supplier/bank
name wrapping to 3+ lines) pushes every subsequent block down instead of
overlapping it — see `_extra_pay_table_height` and the 2026-09-03 fix comment
around line 932 for the bug this closed.

## Content assembly

- `_pick(invoice, *keys, tenant=, tenant_attr=)` — first non-empty of the
  given invoice keys, falling back to a tenant attribute.
- `_pick_from_1c(invoice, *keys, supplier_key=)` — same, but also checks the
  nested `invoice["supplier"][supplier_key]` dict. Used only for fields that
  must come from 1C (IIK/BIK/bank/KNP/contract) — no tenant fallback here;
  the only place `Tenant.invoice_*` fallback enters at all is upstream in
  `invoice_pdf_cache.py` via `_merge_supplier_requisites`.
- `_item_name_with_payment_month(name, invoice_date, also_shift_operations=)`
  — appends "за <Месяц> <Год>г" to a line item's name, computed from the
  invoice date. Rent lines shift +1 month (invoiced in advance for next
  month); utilities/operations use the invoice's own month, *except* for
  tenants with `Tenant.invoice_operations_advance_billing=True` (Maxi Mall/
  Astranium), which also shift operations by +1. Skips adding a month marker
  if the raw 1C text already names one (expense-reimbursement lines carry
  their own, possibly-different, period).
- `_amount_words_only(amount)` — amount spelled out in Russian words via
  `num2words`, falls back to numeric formatting if that import/call fails.

## Gotchas

- `tenant_has_formal_invoice()` always returns `True` — no longer a real gate,
  kept as a stable call site.
- `_resolve_render_tenant` returns `None` (caller then returns `None` too)
  only when there's neither a real tenant nor enough invoice data
  (name/items/amount) to synthesize one.
