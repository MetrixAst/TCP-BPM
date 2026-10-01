"""Правила статуса оплаты счёта (единый порог для OData/COM/sync)."""

# Счёт считается оплаченным ПОЛНОСТЬЮ только когда покрыт целиком — с небольшим
# допуском на округление сумм в 1С (тот же допуск, что уже используется для
# сверки сумм в counterparty_name_match.AMOUNT_MATCH_TOLERANCE). Раньше порог
# был 80% от суммы — счёт мог считаться "оплачен" при реальном долге в 20%.
PAID_TOLERANCE = 2.0


def paid_enough(invoice_amount: float, paid_amount: float) -> bool:
    """True — оплачено полностью (с допуском на округление). Не отличает
    "ничего не оплачено" от "оплачено частично" — для этого см. payment_coverage_status."""
    amount = float(invoice_amount or 0)
    paid = float(paid_amount or 0)
    if amount <= 0:
        return paid > 0
    return paid >= amount - PAID_TOLERANCE


def payment_coverage_status(invoice_amount: float, paid_amount: float) -> str:
    """"paid" | "partial" | "unpaid" — только по сумме, без учёта срока оплаты
    (просрочку поверх этого накладывает вызывающий код: overdue важнее partial)."""
    amount = float(invoice_amount or 0)
    paid = float(paid_amount or 0)
    if paid_enough(amount, paid):
        return "paid"
    if paid > 0:
        return "partial"
    return "unpaid"
