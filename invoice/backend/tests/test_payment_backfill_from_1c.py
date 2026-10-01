"""Post-sync backfill: amount tolerance and safe field updates."""

from app.services.counterparty_name_match import amounts_near


class TestAmountsNear:
    def test_exact_match(self):
        assert amounts_near(3342730.64, 3342730.64)

    def test_rounding_tolerance(self):
        assert amounts_near(3342731.0, 3342730.64)
        assert amounts_near(923666.0, 923666.24)

    def test_outside_tolerance(self):
        assert not amounts_near(3342731.0, 3342700.0)

    def test_none_safe(self):
        assert not amounts_near(None, 100.0)
