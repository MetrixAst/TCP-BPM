"""Formal invoice PDF for an xlsx-imported TenantPayment row.

xlsx-import (see app/services/xlsx_import/) only ever produced flat
reconciliation rows — TenantPayment(source="xlsx"): amount, period,
charge_type, counterparty name/BIN, no line items, and a synthetic
invoice_id ("xlsx:<tenant_id>:<period>:<cp_key>:<charge_type>", see
normalize.py) that deliberately can never collide with a real 1C GUID.
There was never any way to hand a tenant a PDF for one of these rows —
every download path (download_1c_invoice, both 1C clients' download_
invoice_file, invoice_pdf_cache) requires a real 1C invoice_id and does
a live-or-cached-from-live 1C ownership check (see _guid_literal /
assert_invoice_belongs_to_counterparty) that an "xlsx:..." key can never
pass. Decided 2026-08-31 to build a separate, self-contained path instead
of trying to bend those 1C-specific gates to fit non-1C data.

Renders through the SAME formal-invoice layout used for real 1C invoices
(invoice_report.generate_formal_invoice_document) — by explicit product
decision (2026-08-31) presented identically to a real invoice, with no
"not an original 1C document" marking. Each row becomes exactly one line
item (the row's own charge_type+period, as one lump sum) — also an
explicit decision, not a limitation: _normalize_items() in
invoice_report.py already synthesizes a single item this way whenever
"items" is omitted and "amount" is set, so no manual item list is built
here.

Supplier requisites (IIK/BIK/bank name/KBE/address/contract text) are
filled in from the tenant record via the same _merge_supplier_requisites()
the 1C paths use — reused, not reimplemented, so a tenant's requisites
stay defined in exactly one place regardless of where its invoices
actually come from.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.client_1c.exceptions import MissingSupplierRequisitesError
from app.models.catalog import CounterpartyPhone, Tenant
from app.models.payment import TenantPayment
from app.services.counterparty_cache_service import find_counterparty_in_cache
from app.services.invoice_access import normalize_counterparty_id
from app.services.invoice_service_type import DEFAULT_KNP_BY_SERVICE_TYPE
from app.services.invoice_report import (
    _MONTHS_RU_NOM,
    generate_formal_invoice_document,
)
from app.services.nova_buh_1c_client import (
    _merge_supplier_requisites,
    _pdf_payload_has_supplier_banks,
    _resolve_downloads_path,
)
from app.services.payment_service import _PAYMENT_TYPE_LABELS


def assert_xlsx_payment_accessible(
    payment: Optional[TenantPayment],
    tenant_id: Optional[int],
) -> TenantPayment:
    """tenant_id is what scoped_tenant_id resolved to for this request —
    None means an admin request with no tenant filter (see
    app/api/tenant_scope.py:resolve_tenant_id), any other value is a
    tenant/TRC login already locked to that one tenant. A payment row
    with tenant_id=None (unmatched legacy row, see payment.py's own
    comment on that column) must never be reachable by a locked
    tenant/TRC login — only by an unrestricted admin request."""
    if payment is None:
        raise HTTPException(status_code=404, detail="Счёт не найден")
    if payment.source != "xlsx":
        raise HTTPException(
            status_code=400,
            detail="Этот счёт не из Excel-загрузки — используйте /1c/invoices/{id}/download",
        )
    if tenant_id is not None and payment.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Счёт не принадлежит этому арендатору")
    return payment


# КНП (код назначения платежа) по типу начисления — запрошено 2026-09-03
# для Maxi Mall: 855 для аренды, 856 для коммунальных услуг. Использует ту
# же карту DEFAULT_KNP_BY_SERVICE_TYPE, что и 1С-путь с 2026-09-02
# (_merge_supplier_requisites в nova_buh_1c_client.py — там она применяется,
# когда в самом документе 1С КНП пусто), чтобы коды не расходились между
# путями и не редактировались в двух местах. xlsx-строка всегда несёт РОВНО
# один service_type (не через запятую, как у некоторых 1С-счетов — см.
# normalize.py, один RawChargeRow = один charge_type), так что здесь не
# нужна логика разбора нескольких типов, как в _service_label. xlsx никогда
# не производит service_type="operations" (нет такой категории в
# normalize.py — только rent/utilities/debt/other), так что запись
# "operations" из общей карты здесь фактически недостижима, но остаётся
# общим источником правды.
_SERVICE_TYPE_KNP = DEFAULT_KNP_BY_SERVICE_TYPE


def _period_label(period: str) -> str:
    try:
        year_s, month_s = period.split("-")
        return f"{_MONTHS_RU_NOM[int(month_s)]} {year_s}"
    except (ValueError, IndexError, KeyError):
        return period or ""


def _service_label(service_type: Optional[str]) -> str:
    # .lower() to match _PAYMENT_TYPE_LABELS' keys and the rent check in
    # _line_item_name below — real xlsx data is always lowercase already
    # (normalize.py hardcodes "rent"/"utilities"/"debt"/"other"), but the
    # two case-sensitivity assumptions must still agree with each other.
    parts = [p.strip().lower() for p in (service_type or "").split(",") if p.strip()]
    if not parts:
        return "Услуги"
    return " + ".join(_PAYMENT_TYPE_LABELS.get(p, p) for p in parts)


def _line_item_name(payment: TenantPayment) -> str:
    """Real bug found 2026-09-03: for rent, invoice_report.py's shared
    renderer (_item_name_with_payment_month, called on every item name for
    both 1C and xlsx invoices alike) already shifts the displayed month by
    +1 — a rent invoice dated in August is billed IN ADVANCE for September
    occupancy (see that function's own docstring: "счёт от 20 августа —
    про аренду за сентябрь"). But it only applies that shift when the item
    name does NOT already look like it names a month — building
    "Аренда за Август 2026" here ourselves made its de-dup check think the
    month was already right and skip the shift entirely, so xlsx rent
    invoices silently showed the SOURCE sheet's own month instead of the
    month actually being billed for.

    Fix: for rent specifically, return the bare label with no period at
    all — invoice_report.py computes and appends "за <следующий месяц>"
    itself from payment.invoice_date (unchanged, still the source sheet's
    own date — only the ITEM TEXT reflects the +1 shift, matching exactly
    how 1C-sourced rent invoices already read). Utilities/debt/other are
    billed for the period they're already labeled with (no shift, see the
    same docstring) — keep including it explicitly, unchanged from
    before."""
    label = _service_label(payment.service_type)
    if (payment.service_type or "").strip().lower() == "rent":
        return label
    return f"{label} за {_period_label(payment.period)}"


def _counterparty_phone(db: Session, tenant: Tenant, counterparty_id: str, counterparty_cache: Optional[dict]) -> str:
    """CounterpartyPhone (admin-managed, per-service routing table) is the
    source of truth when it has something — an admin's manual entry there
    deliberately overrides whatever 1C says (see the table's own docstring
    in app/models/catalog.py). But for a COM/Nova tenant that has never had
    anyone enter a phone there, falling straight back to "" throws away
    real phone data that may already be sitting in CounterpartyCache from
    an ordinary background 1C sync (get_counterparties() DOES populate
    "phoneNumber" for COM tenants when the org's own Nova script exposes
    it — confirmed 2026-09-01 against real org 119 data — the earlier
    assumption that COM never has phones was about the ADMIN-WRITE path,
    not this read). counterparty_cache is the dict already fetched by the
    caller (build_xlsx_invoice_payload) — reused, not re-queried."""
    if not counterparty_id:
        return ""
    row = (
        db.query(CounterpartyPhone)
        .filter(
            CounterpartyPhone.trc_id == tenant.trc_id,
            CounterpartyPhone.one_c_counterparty_id == counterparty_id,
        )
        .first()
    )
    if row and row.phone:
        return row.phone
    return str((counterparty_cache or {}).get("phoneNumber") or "").strip()


def build_xlsx_invoice_payload(db: Session, payment: TenantPayment, tenant: Tenant) -> dict:
    counterparty = None
    if payment.counterparty_id:
        counterparty = find_counterparty_in_cache(db, tenant.id, payment.counterparty_id)

    counterparty_name = (
        (counterparty or {}).get("fullName") or payment.tenant_name or payment.ip_name or ""
    )
    counterparty_bin = (counterparty or {}).get("bin") or ""

    payload = {
        "number": str(payment.id),
        "date": payment.invoice_date.isoformat() if payment.invoice_date else "",
        "currency": "KZT",
        "amount": float(payment.amount or 0),
        "service_name": _line_item_name(payment),
        "counterparty_id": payment.counterparty_id or "",
        "counterparty_name": counterparty_name,
        "counterparty_bin": counterparty_bin,
        "counterparty_phone": _counterparty_phone(db, tenant, payment.counterparty_id or "", counterparty),
    }
    knp = _SERVICE_TYPE_KNP.get((payment.service_type or "").strip().lower())
    if knp:
        # Set BEFORE the merge below, not after: _merge_supplier_requisites
        # only fills a field when it's still empty, so this always wins
        # over tenant.invoice_payment_knp for rent/utilities rows, while
        # debt/other/unknown rows (not in the map) still fall through to
        # the tenant's own general KNP as before.
        payload["payment_knp"] = knp
    return _merge_supplier_requisites(payload, tenant)


def render_xlsx_invoice_pdf(db: Session, payment: TenantPayment, tenant: Tenant) -> Optional[str]:
    if payment.amount is None:
        raise HTTPException(
            status_code=422,
            detail="У этой строки нет суммы — нечего указать в счёте",
        )
    payload = build_xlsx_invoice_payload(db, payment, tenant)
    # Same rule the 1C paths enforce (see _pdf_payload_has_supplier_banks
    # callers in nova_buh_1c_client.py / odata_1c_client.py): a PDF invoice
    # with no way to actually receive payment is useless to whoever gets
    # it, regardless of whether the underlying data came from 1C or xlsx.
    # Real local tenant found without these during 2026-08-31 testing (an
    # xlsx-only test tenant that never had IIK/BIK entered) — not a
    # hypothetical case.
    if not _pdf_payload_has_supplier_banks(payload):
        raise MissingSupplierRequisitesError(
            "У арендатора не заполнены банковские реквизиты (IIK/BIK) — "
            "заполните их в карточке арендатора, чтобы формировать счета."
        )
    # Filename keyed by invoice_id (not payment.id) on purpose: the WhatsApp
    # worker's _pdf_matches_invoice() (whatsapp_jobs.py) checks that a
    # pre-supplied file_path's *filename* contains the invoice_id before
    # trusting it — a mismatch silently discards the attachment and falls
    # through to a live 1C re-fetch, which can never succeed for a
    # synthetic "xlsx:..." id. payment.invoice_id is already unique per row
    # by construction (see normalize.py), so this is a safe key.
    save_path = str(_resolve_downloads_path(payment.invoice_id))
    return generate_formal_invoice_document(payload, save_path, tenant)


def find_latest_xlsx_payment(
    db: Session,
    tenant_id: Optional[int],
    counterparty_id: str,
    *,
    service_type: Optional[str] = None,
) -> Optional[TenantPayment]:
    """Latest source="xlsx" row for a counterparty — the xlsx equivalent of
    invoice_access.find_latest_invoice_id / find_invoice_id_for_service_type,
    which search live 1C invoice lists and can never find anything for a
    synthetic "xlsx:..." id. Used by the WhatsApp send flow (see
    app/api/notifications.py:send_notification) when 1C is unavailable for
    a tenant and the counterparty's invoices only exist as xlsx-imported
    rows — the same "send an invoice via WhatsApp" gap this module's
    PDF-download path already closed for manual downloads.

    tenant_id must be given (not None) — unlike most tenant_id-optional
    lookups elsewhere (None usually means "admin, no restriction"), an
    unscoped search here would match counterparty_id across every tenant,
    and virtual xlsx counterparty ids are hashes of name+BIN, not
    guaranteed globally unique the way real 1C GUIDs are. Callers without a
    concrete tenant_id (e.g. an unrestricted admin request) should not use
    this path at all.
    """
    if not tenant_id:
        return None
    cp_key = normalize_counterparty_id(counterparty_id)
    if not cp_key:
        return None
    query = db.query(TenantPayment).filter(
        TenantPayment.tenant_id == tenant_id,
        TenantPayment.source == "xlsx",
        func.lower(TenantPayment.counterparty_id) == cp_key,
    )
    if service_type:
        st_key = service_type.strip().lower()
        if st_key:
            # service_type is comma-joined when a charge covers several
            # types ("rent,utilities") — substring match, same convention
            # payment_service.py's own filter already uses for this column.
            query = query.filter(TenantPayment.service_type.ilike(f"%{st_key}%"))
    return query.order_by(
        TenantPayment.invoice_date.desc(), TenantPayment.id.desc()
    ).first()
