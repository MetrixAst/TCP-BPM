"""Bug report 2026-09-14 (Astranium / Toys market invoice #00000003340):
1C line-item descriptions for compensation/reimbursement billing already
carry their own period, in a format the old dedup guard in
_item_name_with_payment_month() never recognized (dash + short month form,
no "за", no year — e.g. "- август"), so our own computed marker got
appended on top, producing garbage like:

    "Возмещение затрат по электроэнергии - август за Сентябрь 2026г"

Worse: the appended month was outright wrong (Сентябрь, guessed from the
invoice date) when the true period was already stated as август — these
utility reimbursement lines are billed a month in arrears, unlike the
"same month as invoice date" assumption the function makes for ordinary
utilities. Since 1C already states the authoritative period whenever the
raw description mentions any month at all, the fix is to never guess/
append our own marker in that case — see invoice_report.py::
_item_name_with_payment_month.
"""
from app.services.invoice_report import _item_name_with_payment_month


class TestSkipsAppendingWhenRawTextAlreadyHasAnyMonth:
    def test_dash_plus_short_month_form_not_duplicated(self):
        name = _item_name_with_payment_month(
            "Возмещение затрат по электроэнергии - август", "2026-09-08"
        )
        assert name == "Возмещение затрат по электроэнергии - август"

    def test_genitive_month_form_not_duplicated(self):
        name = _item_name_with_payment_month(
            "Возмещение затрат по теплоэнергии-августа", "2026-09-08"
        )
        assert name == "Возмещение затрат по теплоэнергии-августа"

    def test_all_six_astranium_line_items_unchanged(self):
        raw_names = [
            "Возмещение затрат по электроэнергии - август",
            "Возмещение затрат по электроэнергии (лифты, эскалаторы, вытяжки)-август",
            "Возмещение затрат по электроэнергии (вентиляция и кондиционирование)-август",
            "Возмещение затрат по водоснабжению и канализации-август",
            "Возмещение затрат по вывозу ТБО-август",
            "Возмещение затрат по теплоэнергии-август",
        ]
        for raw in raw_names:
            assert _item_name_with_payment_month(raw, "2026-09-08") == raw

    def test_still_shifts_normally_when_no_month_mentioned(self):
        # Regression guard: unrelated lines with no month reference at all
        # must keep getting our computed marker appended, unchanged.
        name = _item_name_with_payment_month("Аренда нежилого помещения", "2026-08-20")
        assert name == "Аренда нежилого помещения за Сентябрь 2026г"

    def test_reprocessing_already_marked_text_is_still_idempotent(self):
        once = _item_name_with_payment_month("Аренда нежилого помещения", "2026-08-20")
        twice = _item_name_with_payment_month(once, "2026-08-20")
        assert once == twice
