from app.services.payment_status_rules import (
    PAID_TOLERANCE,
    paid_enough,
    payment_coverage_status,
)


def test_paid_enough_requires_full_coverage_within_tolerance():
    assert paid_enough(1000, 1000) is True
    assert paid_enough(1000, 1000 - PAID_TOLERANCE) is True
    assert paid_enough(1000, 1000 - PAID_TOLERANCE - 0.01) is False


def test_paid_enough_rejects_the_old_80_percent_threshold():
    """PAID_TOLERANCE replaced an old 80%-coverage rule that let an invoice with
    a real 20% debt read as "paid" (see payment_status_rules.py comment). This
    pins that regression down: 80% coverage must NOT count as paid anymore."""
    assert paid_enough(1000, 800) is False


def test_paid_enough_zero_amount_invoice():
    assert paid_enough(0, 0) is False
    assert paid_enough(0, 5) is True


def test_payment_coverage_status():
    assert payment_coverage_status(1000, 1000) == "paid"
    assert payment_coverage_status(1000, 500) == "partial"
    assert payment_coverage_status(1000, 0) == "unpaid"
