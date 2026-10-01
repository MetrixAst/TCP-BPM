"""Generate invoice PDF when 1C OData does not expose print forms."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlretrieve

from fpdf import FPDF

_FONT_URLS = (
    "https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans.ttf",
    "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/version_2_37/ttf/DejaVuSans.ttf",
)
_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FONT_PATH = _FONT_DIR / "DejaVuSans.ttf"
_SYSTEM_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
)


def _ensure_font() -> Path:
    if _FONT_PATH.exists():
        return _FONT_PATH
    for system_path in _SYSTEM_FONT_CANDIDATES:
        if Path(system_path).exists():
            return Path(system_path)
    _FONT_DIR.mkdir(parents=True, exist_ok=True)
    last_error: Optional[Exception] = None
    for url in _FONT_URLS:
        try:
            urlretrieve(url, _FONT_PATH)
            return _FONT_PATH
        except Exception as e:
            last_error = e
    raise RuntimeError(
        "Не найден шрифт для PDF (кириллица). "
        "Положите DejaVuSans.ttf в backend/app/assets/fonts/ "
        "или установите системный Arial Unicode / DejaVu."
    ) from last_error


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ")


def generate_invoice_pdf(invoice: Dict[str, Any], save_path: str) -> str:
    """
    invoice keys: number, date, counterparty_name, amount, currency, items[]
    item keys: name, quantity, price, amount
    """
    font_path = _ensure_font()
    out = Path(save_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.add_font("InvoiceFont", "", str(font_path))
    pdf.set_font("InvoiceFont", size=11)

    pdf.set_font("InvoiceFont", size=14)
    pdf.cell(0, 10, "Счёт на оплату", ln=True)
    pdf.set_font("InvoiceFont", size=11)
    pdf.ln(4)

    pdf.cell(0, 8, f"Номер: {invoice.get('number') or '—'}", ln=True)
    pdf.cell(0, 8, f"Дата: {invoice.get('date') or '—'}", ln=True)
    pdf.cell(0, 8, f"Контрагент: {invoice.get('counterparty_name') or '—'}", ln=True)
    currency = invoice.get("currency") or "KZT"
    pdf.cell(
        0,
        8,
        f"Сумма: {_fmt_money(float(invoice.get('amount') or 0))} {currency}",
        ln=True,
    )
    pdf.ln(6)

    items: List[Dict[str, Any]] = invoice.get("items") or []
    if items:
        pdf.set_font("InvoiceFont", size=10)
        col_w = (10, 85, 22, 28, 32)
        pdf.cell(col_w[0], 8, "№", border=1)
        pdf.cell(col_w[1], 8, "Наименование", border=1)
        pdf.cell(col_w[2], 8, "Кол-во", border=1)
        pdf.cell(col_w[3], 8, "Цена", border=1)
        pdf.cell(col_w[4], 8, "Сумма", border=1, ln=True)
        line_h = 5.0
        x_row = pdf.l_margin
        for idx, item in enumerate(items, 1):
            name = str(item.get("name") or "")
            qty = item.get("quantity", 0)
            price = float(item.get("price") or 0)
            amount = float(item.get("amount") or 0)
            y_row = pdf.get_y()
            try:
                name_lines = pdf.multi_cell(col_w[1], line_h, name or " ", split_only=True)
                row_h = max(7.0, len(name_lines) * line_h)
            except TypeError:
                row_h = 7.0
            pdf.set_xy(x_row, y_row)
            pdf.cell(col_w[0], row_h, str(idx), border=1)
            pdf.set_xy(x_row + col_w[0] + col_w[1], y_row)
            pdf.cell(col_w[2], row_h, str(qty), border=1)
            pdf.cell(col_w[3], row_h, _fmt_money(price), border=1)
            pdf.cell(col_w[4], row_h, _fmt_money(amount), border=1)
            pdf.set_xy(x_row + col_w[0], y_row)
            pdf.multi_cell(col_w[1], line_h, name or " ", border=1, align="L")
            pdf.set_xy(x_row, y_row + row_h)
    else:
        pdf.cell(0, 8, "Строки счёта не загружены из 1С.", ln=True)

    pdf.ln(8)
    pdf.set_font("InvoiceFont", size=9)
    pdf.multi_cell(
        0,
        5,
        "Документ сформирован автоматически из данных OData 1С "
        "(печатная форма PDF в OData не опубликована).",
    )

    pdf.output(str(out))
    return str(out)
