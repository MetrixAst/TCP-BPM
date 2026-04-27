from django.test import TestCase
from django.db.utils import IntegrityError
from .models import Counterparty
from django.utils import timezone

class CounterpartyModelTest(TestCase):

    def setUp(self):
        self.valid_data = {
            "id_1c": "1C-DEV-001",
            "full_name": "Товарищество с ограниченной ответственностью «Test Company»",
            "short_name": "TOO Test Company",
            "bin_number": "123456789012",
            "bank_accounts": [
                {"bank": "Kaspi", "account": "KZ123..."},
                {"bank": "Halyk", "account": "KZ987..."}
            ]
        }

    def test_counterparty_creation(self):
        cp = Counterparty.objects.create(**self.valid_data)
        self.assertEqual(cp.id_1c, "1C-DEV-001")
        self.assertEqual(cp.short_name, "TOO Test Company")
        self.assertIsInstance(cp.bank_accounts, list)
        self.assertEqual(len(cp.bank_accounts), 2)

    def test_duplicate_id_1c(self):
        Counterparty.objects.create(**self.valid_data)
        
        duplicate_data = self.valid_data.copy()
        duplicate_data["bin_number"] = "000000000000" 
        
        with self.assertRaises(IntegrityError):
            Counterparty.objects.create(**duplicate_data)

    def test_duplicate_bin_number(self):
        Counterparty.objects.create(**self.valid_data)
        
        duplicate_data = self.valid_data.copy()
        duplicate_data["id_1c"] = "1C-NEW-999" 
        
        with self.assertRaises(IntegrityError):
            Counterparty.objects.create(**duplicate_data)

    def test_json_field_read_write(self):
        accounts = [{"id": 1, "iban": "KZ111"}, {"id": 2, "iban": "KZ222"}]
        cp = Counterparty.objects.create(
            id_1c="JSON-TEST",
            full_name="JSON Test",
            short_name="JT",
            bank_accounts=accounts
        )
        
        cp_from_db = Counterparty.objects.get(id=cp.id)
        self.assertEqual(cp_from_db.bank_accounts[0]["iban"], "KZ111")
        self.assertEqual(cp_from_db.bank_accounts[1]["iban"], "KZ222")

    def test_str_method(self):
        cp = Counterparty.objects.create(**self.valid_data)
        self.assertEqual(str(cp), "TOO Test Company")
        
        cp_no_short = Counterparty.objects.create(
            id_1c="1C-NO-SHORT",
            full_name="Только Полное Имя",
            short_name=""
        )
        self.assertEqual(str(cp_no_short), "Только Полное Имя")