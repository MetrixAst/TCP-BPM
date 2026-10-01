"""app/services/invoice_report.py — two real layout bugs found 2026-09-03
while reviewing a real prod invoice PDF (tenant "Astranium", a long
company name wrapping to 3 lines in the "Образец платежного поручения"
table):

1. The invoice title ("Счет на оплату № ... от ...") and its underline
   rendered ON TOP of the payment-details table instead of below it,
   because every fixed Y position after that table (via the yp() closure)
   assumed the table's reference height (H_PAY_BLOCK1 + H_PAY_BLOCK2) and
   never adjusted upward when a long name made it taller.
2. The stamp image overlapped the "Всего к оплате: ..." text and the
   footer rule above it — reproduced even WITHOUT bug #1 (a short supplier
   name, e.g. "Maxi Mall (test)") — the stamp's actual rendered height
   (34mm, centered on an 18mm signature box) reaches further up than the
   fixed 10mm block offset left room for.

No PDF-parsing library is available in this environment (pdfplumber/
PyPDF2/pymupdf all absent) to assert on rendered text/image positions
directly, so these tests target the extracted pure arithmetic (bug #1)
and a documented geometric invariant on the layout constants (bug #2),
plus a smoke-render proving the full pipeline still produces a valid PDF
for the exact scenario that exposed both bugs."""
from pathlib import Path
from unittest.mock import MagicMock

from app.services.invoice_report import (
    EXEC_SIGN_BLOCK_Y_OFFSET_MM,
    EXEC_SIGNATURE_H,
    EXEC_STAMP_H,
    FOOTER_RULE_TO_EXECUTOR_MM,
    H_PAY_BLOCK1,
    H_PAY_BLOCK2,
    _extra_pay_table_height,
    generate_formal_invoice_document,
)


class TestExtraPayTableHeight:
    def test_reference_size_table_needs_no_extra_shift(self):
        """The common case: short beneficiary/bank names fit within the
        reference layout's assumed row heights exactly — 0 extra shift,
        byte-identical behavior to before this fix existed."""
        assert _extra_pay_table_height(H_PAY_BLOCK1, H_PAY_BLOCK2) == 0.0

    def test_smaller_than_reference_still_zero(self):
        """A block can render SHORTER than the reference minimum (the
        pay_row_stacked call itself already clamps to min_block_h, but
        this function must not go negative either way)."""
        assert _extra_pay_table_height(H_PAY_BLOCK1 - 5, H_PAY_BLOCK2 - 5) == 0.0

    def test_taller_first_row_shifts_by_the_excess(self):
        """The actual bug scenario: a long beneficiary name wraps to an
        extra line, growing row 1 past its reference height."""
        extra = _extra_pay_table_height(H_PAY_BLOCK1 + 6.0, H_PAY_BLOCK2)
        assert abs(extra - 6.0) < 1e-6

    def test_both_rows_taller_sum_independently(self):
        extra = _extra_pay_table_height(H_PAY_BLOCK1 + 6.0, H_PAY_BLOCK2 + 3.0)
        assert abs(extra - 9.0) < 1e-6


class TestStampClearsFooterRule:
    def test_stamp_top_edge_stays_below_the_footer_rule(self):
        """The actual bug: the stamp is centered on an 18mm signature box
        but is itself 34mm tall, so its real top edge sits
        (EXEC_STAMP_H - EXEC_SIGNATURE_H)/2 above the block's anchor
        point. That anchor is EXEC_SIGN_BLOCK_Y_OFFSET_MM below the
        "Исполнитель" line — this asserts the stamp's real top edge still
        ends up BELOW (further from "Исполнитель" than) the footer rule
        that sits FOOTER_RULE_TO_EXECUTOR_MM above it, i.e. never reaches
        back up into the "Всего к оплате" text above the rule. Fails
        against the old constant (-10mm offset) which put the stamp's
        real top edge 18mm above "Исполнитель" - past an 8mm-above rule."""
        real_top_edge_offset = EXEC_SIGN_BLOCK_Y_OFFSET_MM - (EXEC_STAMP_H - EXEC_SIGNATURE_H) / 2
        assert real_top_edge_offset > -FOOTER_RULE_TO_EXECUTOR_MM

    def test_old_offset_would_have_failed_this_invariant(self):
        """Confirms the test above actually catches the real bug, rather
        than being vacuously true for any constant."""
        old_offset = -10.0
        old_real_top_edge_offset = old_offset - (EXEC_STAMP_H - EXEC_SIGNATURE_H) / 2
        assert old_real_top_edge_offset <= -FOOTER_RULE_TO_EXECUTOR_MM


class TestFullRenderWithLongSupplierNameAndStamp:
    def _tenant(self, tmp_path):
        stamp_path = tmp_path / "stamp.png"
        # 1x1 transparent PNG - enough for fpdf2 to embed without needing
        # a real stamp image; only the layout math is under test here.
        stamp_path.write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d4948445200000001000000010806"
                "0000001f15c4890000000a49444154789c6360000002000100"
                "ffff03000006000557bfabd40000000049454e44ae426082"
            )
        )
        tenant = MagicMock()
        tenant.id = 1
        tenant.name = "Astranium"
        tenant.legal_name = 'Товарищество с ограниченной ответственностью "Astranium"'
        tenant.stamp_file_path = str(stamp_path)
        tenant.signature_file_path = None
        tenant.stamp_png = None
        tenant.signature_png = None
        return tenant

    def test_renders_without_error_and_produces_a_real_pdf(self, tmp_path):
        tenant = self._tenant(tmp_path)
        payload = {
            "number": "00000003060",
            "date": "2026-09-10",
            "currency": "KZT",
            "amount": 2344012,
            "vat": 323312,
            "counterparty_name": "Admix Sport (Адмикс Спорт) ТОО",
            "counterparty_bin": "220240009868",
            "service_name": "Арендная плата за Октябрь 2026г",
            "supplier_name": tenant.legal_name,
            "supplier_bin": "221140001217",
            "supplier_iik": "KZ5596506F0007961193",
            "supplier_bik": "IRTYKZKA",
            "supplier_bank_name": "Филиал АО Forte Bank",
        }
        out = tmp_path / "invoice.pdf"

        result = generate_formal_invoice_document(payload, str(out), tenant)

        assert result is not None
        assert Path(result).is_file()
        assert Path(result).stat().st_size > 1000  # not an empty/broken file
