from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from urllib.request import urlretrieve

from fpdf import FPDF

from app.services.invoice_pdf import _ensure_font
from app.services.invoice_service_type import DEFAULT_PAYMENT_KEYWORDS
from app.services.tenant_stamp import resolve_signature_path, resolve_stamp_path

if TYPE_CHECKING:
    from app.models.catalog import Tenant

logger = logging.getLogger(__name__)

# Макет по эталону что скинул Жанибек
REFERENCE_PDF_PATH = (
    Path(__file__).resolve().parent.parent
    / "assets"
    / "reference_invoice_18490.pdf"
)

_PT_TO_MM = 210 / 595.32


def _pt_mm(pt: float) -> float:
    return pt * _PT_TO_MM


# Координаты из эталонного PDF
X_PAY_LEFT = _pt_mm(36.73)
X_PAY_IIK = _pt_mm(315.85)
X_PAY_KBE = _pt_mm(432.25)
X_PAY_RIGHT = _pt_mm(565.33)
X_LABEL = _pt_mm(38.6)
X_VALUE = _pt_mm(126.4)
X_PHONE_RIGHT = _pt_mm(317.5)
X_SIGN = _pt_mm(368.0)

# Вертикальные позиции
Y_NOTICE = _pt_mm(35.0)
NOTICE_TOP_GAP = 2.5
NOTICE_VALIDITY_GAP = 3.0
PAY_AFTER_VALIDITY_GAP = 5.0
Y_PAY_TITLE = _pt_mm(95.6)
Y_PAY_GRID = _pt_mm(107.5)
H_PAY_BLOCK1 = _pt_mm(36.4)
H_PAY_BLOCK2 = _pt_mm(24.5)
Y_INVOICE_TITLE = _pt_mm(183.1)
Y_SUPPLIER_VALUE = _pt_mm(221.0)
Y_SUPPLIER_LABEL = _pt_mm(226.9)
Y_PHONE_ROW1 = _pt_mm(247.0)
Y_PHONE_ROW2 = _pt_mm(258.9)
Y_BUYER = _pt_mm(281.4)
Y_BASIS = _pt_mm(306.1)
Y_TABLE_HEAD = _pt_mm(330.8)
TBL_HEAD_H = _pt_mm(12.8)
TBL_ROW_H = _pt_mm(10.7)
TBL_TOTALS_GAP = 3.0
TBL_TOTAL_FONT_SIZE = 9.7
SUMMARY_AFTER_TOTALS_MM = 4.0
SUMMARY1_TO_SUMMARY2_MM = 5.0
SUMMARY_LINE_H_MM = 4.0
SUMMARY_TO_FOOTER_RULE_MM = 6.0
FOOTER_RULE_TO_EXECUTOR_MM = 8.0
EXEC_SIGN_TEXT_OFFSET_MM = 2.4
# Real bug found 2026-09-03: the stamp (EXEC_STAMP_H=34mm) is centered on
# an 18mm-tall signature box, so its actual top edge sits (34-18)/2=8mm
# ABOVE whatever Y this offset anchors the block to. The old value (-10,
# i.e. 10mm above the "Исполнитель" line) put the stamp's real top edge
# 18mm above "Исполнитель" — reaching past FOOTER_RULE_TO_EXECUTOR_MM's
# own hrule (8mm above "Исполнитель") and into the "Всего к оплате" text
# above it, on EVERY invoice that has both a stamp and this text (not
# something this session's other fix introduced — reproduced against the
# very first working xlsx invoice too). +3 puts the real top edge 5mm
# above "Исполнитель" — comfortably below the hrule, never touching the
# summary text.
EXEC_SIGN_BLOCK_Y_OFFSET_MM = 3.0
Y_SUMMARY1 = _pt_mm(413.6)
Y_SUMMARY2 = _pt_mm(424.2)
Y_FOOTER_RULE = _pt_mm(448.0)
Y_EXECUTOR = _pt_mm(507.9)
Y_SIGN = _pt_mm(510.3)
# Блок подписи+печати: подпись снизу, печать поверх
X_EXEC_SIGN = _pt_mm(145)
EXEC_SIGNATURE_W = 42
EXEC_SIGNATURE_H = 18
EXEC_STAMP_W = 34
EXEC_STAMP_H = 34

RULE_WIDTH_MM = 0.65
TBL_OUTER_LINE = 0.45
TBL_INNER_LINE = 0.15
TITLE_HEIGHT_MM = 8.0
TITLE_RULE_GAP_MM = 4.0
TBL_HEAD_FONT_SIZE = 9.7
TBL_DATA_FONT_SIZE = 7.9
_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_BOLD_FONT_CANDIDATES = (
    _FONT_DIR / "DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
)

# Таблица товаров — границы колонок по вертикальным линиям
X_TBL_LEFT = _pt_mm(37.82)
X_TBL_NO = _pt_mm(57.49)
X_TBL_QTY = _pt_mm(316.57)
X_TBL_UNIT = _pt_mm(367.33)
X_TBL_PRICE = _pt_mm(405.01)
X_TBL_SUM = _pt_mm(465.37)
X_TBL_RIGHT = _pt_mm(538.46)

_MONTHS_RU = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

# именительный — как в 1С: «за Июль 2026г»
_MONTHS_RU_NOM = (
    "",
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)

# Любое упоминание месяца в сыром тексте 1С (родительный «августа», именительный
# «Август», как в «- август» / «-августа» — форматы возмещения затрат) — если
# оно уже есть, значит период уже указан источником и не нужно ни дублировать,
# ни (что хуже) подставлять свой вычисленный месяц поверх, который может не
# совпадать с фактическим (см. _item_name_with_payment_month).
_ANY_MONTH_NAME_LOWER = tuple(
    m.lower() for m in (_MONTHS_RU[1:] + _MONTHS_RU_NOM[1:])
)

NOTICE_TEXT = (
    "Внимание! Оплата данного счета означает согласие с условиями поставки товара.\n"
    "Уведомление об оплате обязательно, в противном случае не гарантируется наличие\n"
    "товара на складе. Товар отпускается по факту прихода денег на р/с Поставщика,\n"
    "самовывозом, при наличии доверенности и документов удостоверяющих личность."
)


def _fmt_money_kzt(value: float) -> str:
    formatted = f"{float(value):,.2f}"
    whole, frac = formatted.split(".")
    return f"{whole.replace(',', ' ')},{frac}"


def _fmt_qty_total(value: float) -> str:

    return f"{float(value):.2f}".replace(".", ",")


def _unit_for_row(unit: str) -> str:
    u = (unit or "").strip().lower()
    if u in ("шт", "штука", "штуки"):
        return "шт"
    if u in ("услуга", "услуги", "усл.", "усл"):
        return "усл"
    return unit or "шт"


def _normalize_item_name(text: str) -> str:
    return " ".join((text or "").replace("\r", "\n").split())


def _payment_month_from_invoice_date(date_str: str, month_offset: int = 0) -> str:
    """Месяц оплаты из даты счёта. month_offset=1 — для аренды: счёт выставляется
    авансом за СЛЕДУЮЩИЙ месяц (счёт от 20 августа — про аренду за сентябрь),
    в отличие от коммуналки/эксплуатации, которые по факту за текущий месяц."""
    raw = (date_str or "").strip().split("T")[0]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            month0 = dt.month - 1 + month_offset
            year = dt.year + month0 // 12
            month = month0 % 12 + 1
            return f"{_MONTHS_RU_NOM[month]} {year}г"
        except ValueError:
            continue
    return ""


def _item_name_with_payment_month(
    name: str, invoice_date: str, *, also_shift_operations: bool = False
) -> str:
    """
    В наименование строки — месяц из даты счёта (как в 1С), со сдвигом +1 месяц
    для строк аренды (выставляется авансом за следующий месяц — см.
    _payment_month_from_invoice_date). Коммуналка/эксплуатация — тот же месяц,
    что и дата счёта (по факту) — ЗА ИСКЛЮЧЕНИЕМ тенантов с
    Tenant.invoice_operations_advance_billing=True (Maxi Mall/Astranium,
    запрошено 2026-09-02: у них эксплуатация и маркетинг тоже авансом за
    следующий месяц, как аренда). Это не глобальное правило — большинство
    ТРЦ выставляют эксплуатацию по факту, поэтому сдвиг для неё включается
    только по явному флагу конкретного тенанта, не по одним ключевым словам.
    «Коммунальные платежи (электроэнергия)» →
    «Коммунальные платежи за Июль 2026г (электроэнергия)»
    «Аренда нежилого помещения», счёт от 20.08 →
    «Аренда нежилого помещения за Сентябрь 2026г»
    """
    base = _normalize_item_name(name)
    if not base:
        return base
    low = base.lower()
    is_rent = any(kw in low for kw in DEFAULT_PAYMENT_KEYWORDS.rent)
    is_ops = also_shift_operations and any(
        kw in low for kw in DEFAULT_PAYMENT_KEYWORDS.operations
    )
    period = _payment_month_from_invoice_date(
        invoice_date, month_offset=1 if (is_rent or is_ops) else 0
    )
    if not period:
        return base
    low = base.lower()
    # Сырое название уже содержит месяц в любом виде — «за Июль 2026г» (наш же
    # маркер при повторной обработке) или «- август» / «-августа» (как 1С сам
    # подписывает возмещение затрат). В обоих случаях период уже указан и
    # авторитетен — не дублируем и, главное, не подставляем свой вычисленный
    # месяц поверх: для строк возмещения затрат он считается «по факту месяца
    # счёта» и может не совпадать с реальным периодом расходов (счёт от
    # 8 сентября может быть за август — коммуналка выставляется с лагом).
    if any(m in low for m in _ANY_MONTH_NAME_LOWER):
        return base
    marker = f"за {period}"
    if "(" in base:
        head, tail = base.split("(", 1)
        return f"{head.rstrip()} {marker} ({tail}"
    return f"{base} {marker}"


def _resolve_bold_font(regular: Path) -> Path:
    for candidate in _BOLD_FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path
    _FONT_DIR.mkdir(parents=True, exist_ok=True)
    bold_path = _FONT_DIR / "DejaVuSans-Bold.ttf"
    if not bold_path.exists():
        try:
            urlretrieve(
                "https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans-Bold.ttf",
                bold_path,
            )
        except Exception as exc:
            logger.debug("Bold font download skipped: %s", exc)
    if bold_path.exists():
        return bold_path
    return regular


def _draw_hrule(pdf: FPDF, y: float) -> None:

    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(RULE_WIDTH_MM)
    pdf.line(X_TBL_LEFT, y, X_TBL_RIGHT, y)


def _normalize_stacked_text(text: str) -> str:
    return " ".join((text or "").replace("\r", "\n").split())


def _wrap_text_to_width(
    pdf: FPDF,
    text: str,
    width: float,
    *,
    style: str = "",
    size: float = 8.9,
    line_h: float = 4.0,
) -> List[str]:
    normalized = _normalize_stacked_text(text)
    if not normalized:
        return [""]
    max_w = max(width - 1.0, 1.0)
    pdf.set_font("InvoiceFont", style=style, size=size)

    def _fits(line: str) -> bool:
        return pdf.get_string_width(line) <= max_w

    def _split_long_token(token: str) -> List[str]:
        if _fits(token):
            return [token]
        parts: List[str] = []
        current = ""
        for ch in token:
            candidate = current + ch
            if _fits(candidate):
                current = candidate
            else:
                if current:
                    parts.append(current)
                current = ch
        if current:
            parts.append(current)
        return parts or [token]

    try:
        wrapped = pdf.multi_cell(max_w, line_h, normalized, split_only=True)
        if wrapped:
            verified: List[str] = []
            for line in wrapped:
                if _fits(line):
                    verified.append(line)
                else:
                    for word in line.split():
                        verified.extend(_split_long_token(word))
            if verified:
                return verified
    except TypeError:
        pass

    lines: List[str] = []
    current = ""
    for word in normalized.split():
        for piece in _split_long_token(word):
            candidate = f"{current} {piece}".strip()
            if not current or _fits(candidate):
                current = candidate
            else:
                lines.append(current)
                current = piece
    if current:
        lines.append(current)
    return lines or [normalized]


def _stacked_cell_content_height(
    pdf: FPDF,
    width: float,
    lines: List[tuple[str, bool]],
    *,
    size: float = 8.9,
    line_h: float = 4.0,
    pad: float = 0.8,
) -> float:
    inner_w = max(width - 2 * pad, 1.0)
    total = 2 * pad
    for text, is_bold in lines:
        if not text:
            total += line_h
            continue
        style = "B" if is_bold else ""
        wrapped = _wrap_text_to_width(
            pdf, text, inner_w, style=style, size=size, line_h=line_h
        )
        total += max(1, len(wrapped)) * line_h
    return total


def _draw_stacked_cell(
    pdf: FPDF,
    x0: float,
    y0: float,
    width: float,
    block_h: float,
    lines: List[tuple[str, bool]],
    *,
    align: str = "L",
    size: float = 8.9,
    line_h: float = 4.0,
) -> None:

    pad = 0.8
    pdf.rect(x0, y0, width, block_h)
    y_text = y0 + pad
    inner_w = max(width - 2 * pad, 1.0)
    for text, is_bold in lines:
        if not text:
            y_text += line_h
            continue
        style = "B" if is_bold else ""
        for line in _wrap_text_to_width(
            pdf, text, inner_w, style=style, size=size, line_h=line_h
        ):
            pdf.set_font("InvoiceFont", style=style, size=size)
            safe = line
            while safe and pdf.get_string_width(safe) > inner_w:
                safe = safe[:-1]
            pdf.set_xy(x0 + pad, y_text)
            pdf.cell(inner_w, line_h, safe, align=align)
            y_text += line_h


def _table_col_widths() -> tuple[float, float, float, float, float, float]:

    return (
        X_TBL_NO - X_TBL_LEFT,
        X_TBL_QTY - X_TBL_NO,
        X_TBL_UNIT - X_TBL_QTY,
        X_TBL_PRICE - X_TBL_UNIT,
        X_TBL_SUM - X_TBL_PRICE,
        X_TBL_RIGHT - X_TBL_SUM,
    )


def _table_col_x_bounds() -> List[float]:

    widths = _table_col_widths()
    xs = [X_TBL_LEFT]
    for width in widths:
        xs.append(xs[-1] + width)
    return xs


def _draw_table_row_cells(
    pdf: FPDF,
    y: float,
    row_h: float,
    cells: tuple[str, str, str, str, str, str],
    *,
    aligns: tuple[str, str, str, str, str, str] = ("C", "L", "R", "C", "R", "R"),
    font_size: float = 7.9,
    bold: bool = False,
) -> None:

    widths = _table_col_widths()
    pdf.set_font("InvoiceFont", style="B" if bold else "", size=font_size)
    x = X_TBL_LEFT
    for text, width, align in zip(cells, widths, aligns):
        pdf.set_xy(x, y)
        pdf.cell(width, row_h, text, border=0, align=align)
        x += width


def _wrapped_name_line_count(
    pdf: FPDF,
    text: str,
    width: float,
    *,
    font_size: float,
    line_h: float,
) -> int:
    pdf.set_font("InvoiceFont", size=font_size)
    inner_w = max(width - 1.6, 10.0)
    name = _normalize_item_name(text)
    try:
        lines = pdf.multi_cell(inner_w, line_h, name or " ", split_only=True)
        return max(1, len(lines))
    except TypeError:
        # Старые версии fpdf2 без split_only
        return max(1, int(pdf.get_string_width(name) / inner_w) + 1)


def _draw_table_data_row(
    pdf: FPDF,
    y: float,
    cells: tuple[str, str, str, str, str, str],
    *,
    font_size: float = TBL_DATA_FONT_SIZE,
) -> float:
    """Строка таблицы с переносом длинного наименования; возвращает высоту строки."""
    widths = _table_col_widths()
    aligns: tuple[str, str, str, str, str, str] = ("C", "L", "R", "C", "R", "R")
    name_width = widths[1]
    line_h = 3.35
    pad_y = 0.55
    pad_x = 0.8
    name_lines = _wrapped_name_line_count(
        pdf,
        cells[1],
        name_width,
        font_size=font_size,
        line_h=line_h,
    )
    row_h = max(TBL_ROW_H, name_lines * line_h + 2 * pad_y)

    pdf.set_font("InvoiceFont", size=font_size)
    xs = _table_col_x_bounds()
    for col_idx, (text, width, align) in enumerate(zip(cells, widths, aligns)):
        if col_idx == 1:
            continue
        pdf.set_xy(xs[col_idx], y)
        pdf.cell(width, row_h, text, border=0, align=align)

    pdf.set_xy(xs[1] + pad_x, y + pad_y)
    pdf.multi_cell(
        max(name_width - 2 * pad_x, 10.0),
        line_h,
        _normalize_item_name(cells[1]) or " ",
        align="L",
    )

    return row_h


def _draw_table_inner_grid(pdf: FPDF, y_top: float, y_bottom: float, row_lines: List[float]) -> None:

    xs = _table_col_x_bounds()
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(TBL_INNER_LINE)
    for y_line in row_lines:
        pdf.line(xs[0], y_line, xs[-1], y_line)
    for x_line in xs:
        pdf.line(x_line, y_top, x_line, y_bottom)


def _draw_table_outer_border(pdf: FPDF, y_top: float, height: float) -> None:

    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(TBL_OUTER_LINE)
    pdf.rect(X_TBL_LEFT, y_top, X_TBL_RIGHT - X_TBL_LEFT, height)


def _draw_table_totals(
    pdf: FPDF,
    y: float,
    *,
    amount: float,
    vat: float,
    row_h: float = TBL_ROW_H,
) -> float:

    xs = _table_col_x_bounds()
    pdf.set_font("InvoiceFont", style="B", size=TBL_TOTAL_FONT_SIZE)
    label_x = xs[3]
    label_w = xs[5] - xs[3]
    sum_w = xs[6] - xs[5]

    pdf.set_xy(label_x, y)
    pdf.cell(label_w, row_h, "Итого:", border=0, align="R")
    pdf.set_xy(xs[5], y)
    pdf.cell(sum_w, row_h, _fmt_money_kzt(amount), border=0, align="R")
    y += row_h

    pdf.set_xy(label_x, y)
    pdf.cell(label_w, row_h, "В том числе НДС:", border=0, align="R")
    pdf.set_xy(xs[5], y)
    pdf.cell(sum_w, row_h, _fmt_money_kzt(vat), border=0, align="R")
    return y + row_h


def _format_tax_label(bin_value: str, *, label: str = "БИН") -> str:
    if not bin_value:
        return ""
    prefix = "ИИН" if label.upper() == "ИИН" else "БИН"
    return f"{prefix}: {bin_value}"


def _supplier_lines(invoice: Dict[str, Any], tenant: "Tenant") -> List[str]:

    name = _pick(invoice, "supplier_name", tenant=tenant, tenant_attr="legal_name") or tenant.name
    tax = _pick(invoice, "supplier_bin")
    if not tax and tenant.bin_value:
        tax = str(tenant.bin_value).strip()
    if not tax and tenant.iin_value:
        tax = str(tenant.iin_value).strip()
    addr = _pick_from_1c(invoice, "supplier_address", supplier_key="address")
    lines: List[str] = []
    if tax and addr:
        lines.append(f'{name}, БИН: {tax}, Адрес: {addr}')
    elif tax:
        lines.append(f"{name}, БИН: {tax}")
    elif addr:
        lines.append(f"{name}, Адрес: {addr}")
    else:
        lines.append(name)
    phones = list(invoice.get("supplier_phones") or [])
    for idx in range(0, len(phones), 2):
        lines.append("    ".join(phones[idx : idx + 2]))
    return lines


def _buyer_line(invoice: Dict[str, Any]) -> str:

    name = (invoice.get("counterparty_name") or "").strip()
    tax = (invoice.get("counterparty_bin") or "").strip()
    addr = (invoice.get("counterparty_address") or "").strip()
    phone = (invoice.get("counterparty_phone") or "").strip()
    parts: List[str] = []
    if name:
        parts.append(f'"{name}"' if not name.startswith('"') else name)
    if tax:
        parts.append(f"БИН: {tax}")
    if phone:
        parts.append(f"тел.{phone}")
    if addr:
        parts.append(addr)
    return ", ".join(parts) if parts else ""


def _format_invoice_date(date_str: str) -> str:
    raw = (date_str or "").strip().split("T")[0]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return f"{dt.day} {_MONTHS_RU[dt.month]} {dt.year} г."
        except ValueError:
            continue
    return raw


def _amount_words_only(amount: float) -> str:

    value = round(float(amount), 2)
    whole = int(value)
    tyiyns = int(round((value - whole) * 100))
    if tyiyns >= 100:
        whole += tyiyns // 100
        tyiyns = tyiyns % 100
    try:
        from num2words import num2words

        words = num2words(whole, lang="ru").strip()
        if not words:
            raise ValueError("empty num2words result")
        words = words[0].upper() + words[1:]
        return f"{words} тенге {tyiyns:02d} тиын"
    except Exception as exc:
        logger.debug("num2words skipped: %s", exc)
        return f"{_fmt_money_kzt(amount)} тенге {tyiyns:02d} тиын"


def _pick(
    invoice: Dict[str, Any],
    *keys: str,
    tenant: Optional["Tenant"] = None,
    tenant_attr: str = "",
) -> str:
    for key in keys:
        val = invoice.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    if tenant and tenant_attr:
        val = getattr(tenant, tenant_attr, None)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _pick_from_1c(invoice: Dict[str, Any], *invoice_keys: str, supplier_key: str = "") -> str:

    for key in invoice_keys:
        val = invoice.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    if supplier_key:
        supplier = invoice.get("supplier") or {}
        val = supplier.get(supplier_key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _beneficiary_bin(invoice: Dict[str, Any], tenant: "Tenant") -> str:
    tax = _pick(invoice, "supplier_bin")
    label = "БИН"
    if not tax and tenant.bin_value:
        tax = str(tenant.bin_value).strip()
    if not tax and tenant.iin_value:
        tax = str(tenant.iin_value).strip()
        label = "ИИН"
    return _format_tax_label(tax, label=label)


def _executor_signature(tenant: "Tenant", invoice: Dict[str, Any]) -> str:
    name = (
        (tenant.invoice_executor_name or "").strip()
        or _pick(invoice, "executor_name", "responsible_name")
    )
    if not name:
        return ""
    if name.startswith("/") and name.endswith("/"):
        return name
    return f"/{name}/"


def _resolve_render_tenant(
    tenant: Optional["Tenant"],
    invoice: Dict[str, Any],
) -> Optional[Any]:

    if tenant is not None:
        return tenant
    from types import SimpleNamespace

    supplier = invoice.get("supplier") or {}
    name = (invoice.get("supplier_name") or supplier.get("name") or "").strip()
    if not name and not invoice.get("items") and not invoice.get("amount"):
        return None
    return SimpleNamespace(
        name=name or "Поставщик",
        legal_name=name or "Поставщик",
        bin_value=invoice.get("supplier_bin") or supplier.get("bin") or "",
        iin_value=None,
        stamp_file_path=None,
        signature_file_path=None,
        invoice_iik=invoice.get("supplier_iik") or supplier.get("iik") or "",
        invoice_kbe=invoice.get("supplier_kbe") or supplier.get("kbe") or "",
        invoice_bank_name=invoice.get("supplier_bank_name") or supplier.get("bank_name") or "",
        invoice_bank_bik=invoice.get("supplier_bik") or supplier.get("bank_bik") or "",
        invoice_payment_knp=invoice.get("payment_knp") or "",
        invoice_supplier_address=invoice.get("supplier_address") or supplier.get("address") or "",
        invoice_executor_name=invoice.get("invoice_executor_name") or "",
        invoice_contract_text=invoice.get("contract_text") or "Без договора",
    )


def tenant_has_formal_invoice(tenant: Optional["Tenant"]) -> bool:

    return True


def _draw_executor_sign_and_stamp(
    pdf: FPDF,
    *,
    stamp_path: Optional[Path],
    signature_path: Optional[Path],
    signature_text: str,
    y_sign_block: float,
    y_sign_text: float,
) -> None:

    if signature_path:
        try:
            pdf.image(
                str(signature_path),
                x=X_EXEC_SIGN,
                y=y_sign_block,
                w=EXEC_SIGNATURE_W,
                h=EXEC_SIGNATURE_H,
            )
        except Exception as exc:
            logger.warning("Could not embed signature: %s", exc)

    if stamp_path:
        try:
            if signature_path:
                stamp_x = X_EXEC_SIGN + (EXEC_SIGNATURE_W - EXEC_STAMP_W) / 2
                stamp_y = y_sign_block + (EXEC_SIGNATURE_H - EXEC_STAMP_H) / 2
            else:
                stamp_x = X_EXEC_SIGN
                stamp_y = y_sign_block
            pdf.image(
                str(stamp_path),
                x=stamp_x,
                y=stamp_y,
                w=EXEC_STAMP_W,
                h=EXEC_STAMP_H,
            )
        except Exception as exc:
            logger.warning("Could not embed stamp: %s", exc)

    if not signature_path and signature_text:
        pdf.set_font("InvoiceFont", size=7.9)
        pdf.set_xy(X_SIGN, y_sign_text)
        pdf.cell(X_PAY_RIGHT - X_SIGN, 4, signature_text)


def _extra_pay_table_height(h_pay_row1: float, h_pay_row2: float) -> float:
    """How much taller the "Образец платежного поручения" table rendered
    than the reference layout (H_PAY_BLOCK1/H_PAY_BLOCK2) assumed — 0 for
    the common case (short beneficiary/bank names), positive whenever one
    wraps to more lines than the reference did. Everything drawn below
    this table (via the yp() closure in _render_reference_invoice_pdf)
    must shift down by exactly this much, or it renders on top of the
    table's own overflow instead of below it — see the real bug this
    fixed, 2026-09-03."""
    return max(0.0, h_pay_row1 - H_PAY_BLOCK1) + max(0.0, h_pay_row2 - H_PAY_BLOCK2)


def _normalize_items(invoice: Dict[str, Any]) -> List[Dict[str, Any]]:
    amount = float(invoice.get("amount") or 0)
    items: List[Dict[str, Any]] = list(invoice.get("items") or [])
    if not items and amount:
        items = [
            {
                "name": invoice.get("service_name") or "Услуги по договору аренды",
                "quantity": 1,
                "price": amount,
                "amount": amount,
                "unit": "услуга",
            }
        ]
    return items


def _render_reference_invoice_pdf(
    invoice: Dict[str, Any],
    tenant: Any,
    save_path: Path,
) -> str:

    font_path = _ensure_font()
    bold_path = _resolve_bold_font(font_path)
    tenant_id = getattr(tenant, "id", None)
    stamp_path = resolve_stamp_path(
        getattr(tenant, "stamp_file_path", None),
        tenant_id=tenant_id,
        tenant=tenant,
    )
    signature_path = resolve_signature_path(
        getattr(tenant, "signature_file_path", None),
        tenant_id=tenant_id,
        tenant=tenant,
    )
    if getattr(tenant, "stamp_file_path", None) and not stamp_path:
        logger.warning(
            "Stamp not found on disk (path=%s). "
            "Use shared volume TENANT_UPLOADS_DIR on all API pods.",
            tenant.stamp_file_path,
        )
    if getattr(tenant, "signature_file_path", None) and not signature_path:
        logger.warning(
            "Signature not found on disk (path=%s). "
            "Use shared volume TENANT_UPLOADS_DIR on all API pods.",
            tenant.signature_file_path,
        )

    number = invoice.get("number") or "—"
    date_display = _format_invoice_date(str(invoice.get("date") or ""))
    currency = invoice.get("currency") or "KZT"
    amount = float(invoice.get("amount") or 0)
    vat = float(invoice.get("vat") or 0)
    items = _normalize_items(invoice)

    supplier_name = (
        _pick(invoice, "supplier_name", tenant=tenant, tenant_attr="legal_name") or tenant.name
    )
    iik = _pick_from_1c(invoice, "supplier_iik", supplier_key="iik")
    kbe = _pick_from_1c(invoice, "supplier_kbe", supplier_key="kbe")
    bank = _pick_from_1c(invoice, "supplier_bank_name", supplier_key="bank_name")
    bik = _pick_from_1c(invoice, "supplier_bik", supplier_key="bank_bik")
    knp = _pick_from_1c(invoice, "payment_knp")
    contract = _pick_from_1c(invoice, "contract_text") or "Без договора"
    signature = _executor_signature(tenant, invoice)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(0, 0, 0)
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.add_font("InvoiceFont", "", str(font_path))
    pdf.add_font("InvoiceFont", "B", str(bold_path))

    w_pay1 = X_PAY_IIK - X_PAY_LEFT
    w_pay2 = X_PAY_KBE - X_PAY_IIK
    w_pay3 = X_PAY_RIGHT - X_PAY_KBE
    w_value = X_PAY_RIGHT - X_VALUE
    w_label = X_VALUE - X_LABEL

    def font(size: float, *, bold: bool = False) -> None:
        pdf.set_font("InvoiceFont", style="B" if bold else "", size=size)


    notice_w = X_TBL_RIGHT - X_TBL_LEFT
    font(7.9)
    pdf.set_xy(X_TBL_LEFT, Y_NOTICE + NOTICE_TOP_GAP)
    pdf.multi_cell(notice_w, 3.4, NOTICE_TEXT, align="C")
    font(8.9, bold=True)
    pdf.set_xy(X_TBL_LEFT, pdf.get_y() + NOTICE_VALIDITY_GAP)

    y_pay_title = pdf.get_y() + PAY_AFTER_VALIDITY_GAP
    layout_shift = y_pay_title - Y_PAY_TITLE

    def yp(y: float) -> float:
        return y + layout_shift


    font(9.8, bold=True)
    pdf.set_xy(X_PAY_LEFT, y_pay_title)
    pdf.cell(X_PAY_RIGHT - X_PAY_LEFT, 5, "Образец платежного поручения")

    bin_line = _beneficiary_bin(invoice, tenant)
    ben_lines1: List[tuple[str, bool]] = [
        ("Бенефициар:", True),
        (_normalize_stacked_text(supplier_name), True),
    ]
    if bin_line:
        ben_lines1.append((bin_line, False))
    ben_lines2 = [("Банк бенефициара:", False), (_normalize_stacked_text(bank or ""), False)]
    iik_lines = [("ИИК", True), (iik or "", True)]
    kbe_lines = [("Кбе", True), (str(kbe or ""), True)]
    bik_lines = [("БИК", True), (bik or "", True)]
    knp_lines = [("Код назначения платежа", True), (str(knp or ""), True)]

    def pay_row_stacked(
        y0: float,
        min_block_h: float,
        col1: List[tuple[str, bool]],
        col2: List[tuple[str, bool]],
        col3: List[tuple[str, bool]],
        *,
        align2: str = "C",
        align3: str = "C",
    ) -> float:
        block_h = max(
            min_block_h,
            _stacked_cell_content_height(pdf, w_pay1, col1),
            _stacked_cell_content_height(pdf, w_pay2, col2),
            _stacked_cell_content_height(pdf, w_pay3, col3),
        )
        _draw_stacked_cell(pdf, X_PAY_LEFT, y0, w_pay1, block_h, col1, align="L")
        _draw_stacked_cell(pdf, X_PAY_IIK, y0, w_pay2, block_h, col2, align=align2)
        _draw_stacked_cell(pdf, X_PAY_KBE, y0, w_pay3, block_h, col3, align=align3)
        return block_h

    h_pay_row1 = pay_row_stacked(yp(Y_PAY_GRID), H_PAY_BLOCK1, ben_lines1, iik_lines, kbe_lines)
    h_pay_row2 = pay_row_stacked(
        yp(Y_PAY_GRID) + h_pay_row1,
        H_PAY_BLOCK2,
        ben_lines2,
        bik_lines,
        knp_lines,
    )
    # Real bug found 2026-09-03: a supplier/bank name long enough to wrap
    # to 3+ lines (e.g. "Товарищество с ограниченной ответственностью
    # Astranium") makes this table taller than the reference layout
    # (H_PAY_BLOCK1/H_PAY_BLOCK2) assumed — every fixed Y position below it
    # (Y_INVOICE_TITLE onward, via yp()) stayed put, so the title's rule
    # line, and everything after, rendered on top of the now-taller table
    # instead of below it. yp() is a closure over layout_shift (defined
    # above, before this point) — Python looks that variable up fresh on
    # every call, so bumping it here retroactively fixes every yp() call
    # still to come without touching each call site individually. Does
    # NOT affect the pay-table rows just drawn above — their positions
    # were already computed and used before this line runs.
    layout_shift += _extra_pay_table_height(h_pay_row1, h_pay_row2)


    font(13.8, bold=True)
    pdf.set_xy(X_LABEL, yp(Y_INVOICE_TITLE))
    pdf.cell(
        X_PAY_RIGHT - X_LABEL,
        TITLE_HEIGHT_MM,
        f"Счет на оплату № {number} от {date_display}",
    )
    _draw_hrule(pdf, yp(Y_INVOICE_TITLE) + TITLE_HEIGHT_MM + TITLE_RULE_GAP_MM)


    supplier_lines = _supplier_lines(invoice, tenant)
    font(9.7)
    pdf.set_xy(X_LABEL, yp(Y_SUPPLIER_LABEL))
    pdf.cell(w_label, 4.5, "Поставщик:")
    if supplier_lines:
        font(9.7, bold=True)
        pdf.set_xy(X_VALUE, yp(Y_SUPPLIER_VALUE))
        pdf.multi_cell(w_value, 4.2, supplier_lines[0])
        extra_lines = supplier_lines[1:]
        phone_idx = 0
        addr_y = yp(_pt_mm(232.8))
        for extra in extra_lines:
            if "    " in extra and len(extra.split("    ")) == 2:
                left, right = extra.split("    ", 1)
                phone_y = yp(Y_PHONE_ROW1) if phone_idx == 0 else yp(Y_PHONE_ROW2)
                font(7.9, bold=True)
                pdf.set_xy(X_VALUE, phone_y)
                pdf.cell(X_PHONE_RIGHT - X_VALUE, 3.8, left)
                pdf.set_xy(X_PHONE_RIGHT, phone_y)
                pdf.cell(X_PAY_RIGHT - X_PHONE_RIGHT, 3.8, right)
                phone_idx += 1
            else:
                font(9.7, bold=True)
                pdf.set_xy(X_VALUE, addr_y)
                pdf.multi_cell(w_value, 4.2, extra)
                addr_y += 4.2


    buyer = _buyer_line(invoice)
    font(9.7)
    pdf.set_xy(X_LABEL, yp(Y_BUYER))
    pdf.cell(w_label, 4.5, "Покупатель:")
    font(9.7, bold=True)
    pdf.set_xy(X_VALUE, yp(Y_BUYER))
    pdf.multi_cell(w_value, 4.2, buyer or " ")
    # Не фиксированный Y_BASIS: длинный покупатель/договор иначе наслаиваются
    y_after_buyer = pdf.get_y()
    y_basis = max(yp(Y_BASIS), y_after_buyer + 1.5)

    font(9.7)
    pdf.set_xy(X_LABEL, y_basis)
    pdf.cell(w_label, 4.5, "Основание:")
    font(9.7, bold=True)
    pdf.set_xy(X_VALUE, y_basis)
    pdf.multi_cell(w_value, 4.2, contract or " ")

    y_table_top = max(yp(Y_TABLE_HEAD), pdf.get_y() + 2.0)
    y = y_table_top
    grid_lines = [y_table_top]

    _draw_table_row_cells(
        pdf,
        y,
        TBL_HEAD_H,
        ("№", "Наименование товаров(работ, услуг)", "Кол-во", "Ед.", "Цена", "Сумма"),
        aligns=("C", "C", "C", "C", "C", "C"),
        font_size=TBL_HEAD_FONT_SIZE,
        bold=True,
    )
    y += TBL_HEAD_H
    grid_lines.append(y)

    for idx, item in enumerate(items, 1):
        qty = float(item.get("quantity") or 1)
        unit = _unit_for_row(str(item.get("unit") or ""))
        qty_cell = str(int(qty)) if qty == int(qty) else _fmt_qty_total(qty)
        row_h = _draw_table_data_row(
            pdf,
            y,
            (
                str(idx),
                _item_name_with_payment_month(
                    str(item.get("name") or ""),
                    str(invoice.get("date") or ""),
                    also_shift_operations=bool(
                        getattr(tenant, "invoice_operations_advance_billing", False)
                    ),
                ),
                qty_cell,
                unit,
                _fmt_money_kzt(float(item.get("price") or 0)),
                _fmt_money_kzt(float(item.get("amount") or 0)),
            ),
            font_size=TBL_DATA_FONT_SIZE,
        )
        y += row_h
        grid_lines.append(y)

    y_data_bottom = y
    _draw_table_inner_grid(pdf, y_table_top, y_data_bottom, grid_lines)
    _draw_table_outer_border(pdf, y_table_top, y_data_bottom - y_table_top)

    y = _draw_table_totals(
        pdf,
        y_data_bottom + TBL_TOTALS_GAP,
        amount=amount,
        vat=vat,
    )

    y += SUMMARY_AFTER_TOTALS_MM
    font(7.9)
    pdf.set_xy(X_LABEL, y)
    pdf.cell(
        X_PAY_RIGHT - X_LABEL,
        SUMMARY_LINE_H_MM,
        f"Всего наименований {len(items)}, на сумму {_fmt_money_kzt(amount)} {currency}",
    )
    # cell не сдвигает Y — иначе «Всего к оплате» наслаивается на первую строку
    y = y + SUMMARY_LINE_H_MM + SUMMARY1_TO_SUMMARY2_MM
    font(9.7, bold=True)
    pdf.set_xy(X_LABEL, y)
    pdf.multi_cell(
        X_PAY_RIGHT - X_LABEL,
        4.5,
        f"Всего к оплате: {_amount_words_only(amount)}",
    )
    y = pdf.get_y() + SUMMARY_TO_FOOTER_RULE_MM

    _draw_hrule(pdf, y)
    y += FOOTER_RULE_TO_EXECUTOR_MM

    font(9.7, bold=True)
    pdf.set_xy(X_LABEL, y)
    pdf.cell(w_label, 4.5, "Исполнитель")
    _draw_executor_sign_and_stamp(
        pdf,
        stamp_path=stamp_path,
        signature_path=signature_path,
        signature_text=signature,
        y_sign_block=y + EXEC_SIGN_BLOCK_Y_OFFSET_MM,
        y_sign_text=y + EXEC_SIGN_TEXT_OFFSET_MM,
    )

    save_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(save_path))
    return str(save_path)


def generate_formal_invoice_document(
    invoice: Dict[str, Any],
    save_path: str,
    tenant: Optional["Tenant"],
) -> Optional[str]:

    render_tenant = _resolve_render_tenant(tenant, invoice)
    if render_tenant is None:
        return None

    out_pdf = Path(save_path)
    if out_pdf.suffix.lower() != ".pdf":
        out_pdf = out_pdf.with_suffix(".pdf")
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = _render_reference_invoice_pdf(invoice, render_tenant, out_pdf)
        logger.info("Formal invoice PDF (reference layout): %s", result)
        return result
    except Exception as exc:
        logger.exception("Formal invoice generation failed: %s", exc)
        return None
