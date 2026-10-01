from datetime import date

from app.schemas.payment import PaymentFilter


def test_payment_filter_accepts_date_range():
    filters = PaymentFilter(
        period="2026-07",
        date_from=date(2026, 7, 5),
        date_to=date(2026, 7, 10),
        page=1,
        page_size=10,
    )
    assert filters.date_from == date(2026, 7, 5)
    assert filters.date_to == date(2026, 7, 10)
    assert filters.period == "2026-07"
