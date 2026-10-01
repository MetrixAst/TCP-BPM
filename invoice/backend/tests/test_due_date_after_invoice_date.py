"""Срок оплаты (due_date) должен всегда быть строго позже даты счёта.

Реальный кейс, найденный пользователем: счёт от 20.08.2026 (аренда, CityMall,
ИП Ибрагимов) уходил клиенту с сообщением "Крайний срок оплаты: 05.08.2026" —
срок раньше самой даты счёта. Причина: due_date_in_invoice_month() всегда
считала due_day-е число ТЕКУЩЕГО месяца счёта, не заглядывая вперёд, если
due_day (обычно 5) уже прошёл к моменту выставления счёта. Правильный срок
для этого счёта — 05.09.2026.

_invoice_due_dates() в обоих 1С-клиентах (Nova/OData) имеет похожий баг:
"5-е число ПЕРИОДА" корректно только когда счёт датирован заранее (аренда
за июль часто датируется концом июня — тогда due 05.07 позже даты счёта),
но период нередко совпадает с месяцем самого счёта (счёт от 20.08 в
периоде "2026-08"), и тогда результат оказывается раньше даты счёта.
"""
from datetime import date

from app.services.invoice_service_type import due_date_in_invoice_month
from app.services.nova_buh_1c_client import NovaBuh1CClient
from app.services.nova_buh_1c_client import _calculate_due_date as nova_calculate_due_date
from app.services.odata_1c_client import OData1CClient


class TestDueDateInInvoiceMonth:
    def test_real_citymall_case_rolls_to_next_month(self):
        """Счёт от 20.08.2026, due_day=5 — 5-е августа уже прошло."""
        assert due_date_in_invoice_month(date(2026, 8, 20), 5) == date(2026, 9, 5)

    def test_due_day_still_ahead_stays_same_month(self):
        """Счёт от 01.08.2026, due_day=5 — 5-е августа ещё впереди."""
        assert due_date_in_invoice_month(date(2026, 8, 1), 5) == date(2026, 8, 5)

    def test_invoice_dated_exactly_on_due_day_rolls_forward(self):
        """Срок не может совпадать с датой счёта — переносим на след. месяц."""
        assert due_date_in_invoice_month(date(2026, 8, 5), 5) == date(2026, 9, 5)

    def test_december_rolls_into_next_year(self):
        assert due_date_in_invoice_month(date(2026, 12, 20), 5) == date(2027, 1, 5)

    def test_result_always_after_invoice_date(self):
        for day in range(1, 29):
            inv_date = date(2026, 8, day)
            for due_day in (1, 5, 15, 28):
                assert due_date_in_invoice_month(inv_date, due_day) > inv_date


class TestNovaCalculateDueDate:
    """nova_buh_1c_client._calculate_due_date — отдельная от
    due_date_in_invoice_month реализация с тем же исходным багом (была
    invoice_date.replace(day=day), т.е. тот же месяц счёта без переноса)."""

    def test_advances_to_next_month(self):
        assert nova_calculate_due_date(date(2026, 8, 20), 5) == date(2026, 9, 5)

    def test_december_rolls_into_next_year(self):
        assert nova_calculate_due_date(date(2026, 12, 20), 5) == date(2027, 1, 5)

    def test_result_always_after_invoice_date(self):
        for day in range(1, 29):
            inv_date = date(2026, 8, day)
            for due_day in (1, 5, 15, 28):
                assert nova_calculate_due_date(inv_date, due_day) > inv_date


class TestInvoiceDueDatesPeriodBranch:
    """_invoice_due_dates() — период совпадает с месяцем счёта (частый
    случай для счёта, выставленного в середине своего же периода)."""

    def test_nova_period_same_month_as_invoice_rolls_forward(self):
        rent, util, ops = NovaBuh1CClient._invoice_due_dates(
            None,  # type: ignore[arg-type]
            date(2026, 8, 20),
            5,
            10,
            operations_due_day=15,
            period="2026-08",
        )
        assert rent == date(2026, 9, 5)
        assert util == date(2026, 9, 10)
        assert ops == date(2026, 9, 15)

    def test_nova_period_one_month_ahead_of_invoice_stays(self):
        """Аренда за июль датирована концом июня — 5 июля позже даты счёта."""
        rent, util, ops = NovaBuh1CClient._invoice_due_dates(
            None,  # type: ignore[arg-type]
            date(2026, 6, 30),
            5,
            10,
            operations_due_day=15,
            period="2026-07",
        )
        assert rent == date(2026, 7, 5)
        assert util == date(2026, 7, 10)
        assert ops == date(2026, 7, 15)

    def test_odata_period_same_month_as_invoice_rolls_forward(self):
        rent, util, ops = OData1CClient._invoice_due_dates(
            date(2026, 8, 20),
            5,
            10,
            operations_due_day=15,
            period="2026-08",
        )
        assert rent == date(2026, 9, 5)
        assert util == date(2026, 9, 10)
        assert ops == date(2026, 9, 15)
