# invoice_pdf.py

Fallback PDF generator, used when 1C OData doesn't expose a print form for an
invoice. Produces a plain, unstyled "Счёт на оплату" — number/date/
counterparty/amount plus a line-items table.

For the branded/formal layout (matches the reference PDF a client provided),
see `invoice_report.py` instead — that one is what's actually used for
xlsx-imported and most live invoices.

## Functions

- `generate_invoice_pdf(invoice, save_path)` — `invoice` keys: `number`,
  `date`, `counterparty_name`, `amount`, `currency`, `items[]` (each:
  `name`, `quantity`, `price`, `amount`). Writes the PDF to `save_path`,
  returns the path.
- `_ensure_font()` — locates a Cyrillic-capable TTF font: local
  `app/assets/fonts/DejaVuSans.ttf` → a few OS system-font candidates →
  downloads DejaVuSans from jsdelivr/GitHub as last resort. Also used by
  `invoice_report.py`.

Raises `RuntimeError` if no font can be found or downloaded — a PDF without
Cyrillic support isn't usable here.
