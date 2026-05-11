from django.test import TestCase
from django.db.utils import IntegrityError
from .models import Counterparty, Invoice, InvoiceItem
from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from .tasks import sync_counterparties
from unittest.mock import patch, MagicMock
from .tasks import sync_counterparties
from datetime import timedelta

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

class InvoiceIntegrationTest(TestCase):
    def setUp(self):
        self.counterparty = Counterparty.objects.create(
            id_1c="TEST-ID-001",
            full_name="Тестовый Контрагент",
            short_name="ТестКорп",
            bin_number="123456789012"
        )

    def test_invoice_with_counterparty_relationship(self):
        invoice = Invoice.objects.create(
            counterparty=self.counterparty,
            number="INV-001",
            status='created',
            Date=timezone.now()
        )
        self.assertEqual(invoice.counterparty.short_name, "ТестКорп")
        self.assertIn(invoice, self.counterparty.invoices.all())

    def test_invoice_items_aggregation(self):
        invoice = Invoice.objects.create(number="INV-002", status='created')
        item1 = InvoiceItem.objects.create(invoice=invoice, name="Услуга 1", quantity=1, price=100)
        item2 = InvoiceItem.objects.create(invoice=invoice, name="Услуга 2", quantity=1, price=200)
        
        self.assertEqual(invoice.items.count(), 2)
        self.assertIn(item1, invoice.items.all())

    def test_invoice_status_choices(self):
        invoice = Invoice.objects.create(number="INV-003", status='created')
        self.assertEqual(invoice.status, 'created')

    def test_cascade_deletion(self):
        invoice = Invoice.objects.create(number="INV-DELETE")
        InvoiceItem.objects.create(invoice=invoice, name="На удаление", quantity=1, price=50)
        
        invoice_id = invoice.id
        invoice.delete()
        
        self.assertEqual(InvoiceItem.objects.filter(invoice_id=invoice_id).count(), 0)

    def test_invoice_item_calculation(self):
        invoice = Invoice.objects.create(number="INV-CALC")
        item = InvoiceItem.objects.create(
            invoice=invoice,
            name="Товар",
            quantity=5.0,
            price=200.0
        )
        self.assertEqual(item.total, 1000.0) 
        self.assertEqual(item.vat_amount, 120.0) 

class OneCViewsTest(TestCase):
    def setUp(self):
        self.cp = Counterparty.objects.create(
            id_1c="VIEW-TEST-01",
            full_name="Тестовая Компания для Views",
            short_name="ТОО Тест",
            bin_number="987654321098"
        )

    def test_counterparty_list_view_status(self):
        url = reverse('onec:counterparty_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ТОО Тест")

    def test_counterparty_search_api_filtering(self):
        url = reverse('onec:counterparty_search_api')
        response = self.client.get(f"{url}?q=Тест")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(any(item['text'].startswith("ТОО Тест") for item in data['results']))
        
        response_empty = self.client.get(f"{url}?q=qwerty")
        self.assertEqual(len(response_empty.json()['results']), 0)

    def test_counterparty_detail_view(self):
        url = reverse('onec:counterparty_detail', kwargs={'pk': self.cp.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "987654321098")
        self.assertNotContains(response, "<form") 

    def test_invoice_create_get_page(self):
        url = reverse('onec:invoice_create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Выставить новый счет")

    def test_invoice_create_post_success(self):
        url = reverse('onec:invoice_create')
        post_data = {
            'counterparty': self.cp.id,
            'comment': 'Тест создания через POST',
            'item_name[]': ['Товар А', 'Товар Б'],
            'item_qty[]': ['10', '5'],
            'item_price[]': ['100', '200'],
        }
        
        response = self.client.post(url, post_data)
        
        self.assertEqual(response.status_code, 302)
        
        invoice = Invoice.objects.filter(comment='Тест создания через POST').first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.counterparty, self.cp)
        self.assertEqual(invoice.items.count(), 2)
        self.assertEqual(invoice.Sum, 2000.0)

    def test_onec_url_prefix(self):
        list_url = reverse('onec:counterparty_list')
        self.assertTrue(list_url.startswith('/onec/'))

class OneCAPITestCase(APITestCase):
    def setUp(self):
        self.cp = Counterparty.objects.create(
            id_1c="API-001",
            short_name="API Test Company",
            bin_number="111222333444",
            bank_accounts=[{"bank": "TestBank", "account": "KZ000"}]
        )
        self.cp_list_url = reverse('onec:api_counterparty-list')
        self.invoice_list_url = reverse('onec:api_invoice-list')

    def test_get_counterparties_list(self):
        response = self.client.get(self.cp_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['short_name'], "API Test Company")
        self.assertIn('bank_accounts', response.data[0])

    def test_post_counterparty_fails(self):
        data = {"short_name": "New Comp", "bin_number": "000"}
        response = self.client.post(self.cp_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_get_invoices_nested(self):
        inv = Invoice.objects.create(counterparty=self.cp, number="INV-100")
        InvoiceItem.objects.create(invoice=inv, name="Item 1", quantity=1, price=100)
        
        response = self.client.get(self.invoice_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data[0]['items']), 1)
        self.assertEqual(response.data[0]['items'][0]['name'], "Item 1")

    def test_create_invoice_with_items_nested(self):
        data = {
            "counterparty": self.cp.id,
            "comment": "API Nested Order",
            "items": [
                {"name": "Товар 1", "quantity": 2, "price": 500},
                {"name": "Товар 2", "quantity": 1, "price": 1000}
            ]
        }
        response = self.client.post(self.invoice_list_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(InvoiceItem.objects.count(), 2)
        
        invoice = Invoice.objects.first()
        self.assertEqual(invoice.items.count(), 2)


MOCK_COUNTERPARTIES = [
    {
        "id_1c": "SYNC-001",
        "full_name": "ТОО Первая Компания",
        "short_name": "Первая",
        "bin_number": "100000000001",
        "iin": None,
        "address": "г. Алматы, ул. Абая 1",
        "phone": "+77001112233",
        "email": "first@test.kz",
        "is_supplier": True,
        "is_customer": False,
        "bank_accounts": [{"bank": "Kaspi", "account": "KZ001"}],
        "contracts": [],
    },
    {
        "id_1c": "SYNC-002",
        "full_name": "ТОО Вторая Компания",
        "short_name": "Вторая",
        "bin_number": "100000000002",
        "iin": None,
        "address": "г. Астана, пр. Республики 10",
        "phone": "+77009998877",
        "email": "second@test.kz",
        "is_supplier": False,
        "is_customer": True,
        "bank_accounts": [],
        "contracts": [{"number": "ДГ-001"}],
    },
]
 
 
class SyncCounterpartiesTaskTest(TestCase):
    def _patch_client(self, return_value=None, side_effect=None):
        patcher = patch("onec.client_1c.client.Client1C")
        mock_cls = patcher.start()
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
 
        if side_effect:
            mock_instance.get_counterparties.side_effect = side_effect
        else:
            mock_instance.get_counterparties.return_value = return_value or []
 
        self.addCleanup(patcher.stop)
        return mock_instance
 
 
    def test_sync_creates_new_counterparties(self):
        self._patch_client(return_value=MOCK_COUNTERPARTIES)
 
        result = sync_counterparties()
 
        self.assertEqual(Counterparty.objects.count(), 2)
        self.assertIn("создано 2", result)
        self.assertIn("обновлено 0", result)
 
    def test_sync_creates_correct_field_values(self):
        self._patch_client(return_value=MOCK_COUNTERPARTIES[:1])
 
        sync_counterparties()
 
        cp = Counterparty.objects.get(id_1c="SYNC-001")
        self.assertEqual(cp.full_name, "ТОО Первая Компания")
        self.assertEqual(cp.short_name, "Первая")
        self.assertEqual(cp.bin_number, "100000000001")
        self.assertEqual(cp.email, "first@test.kz")
        self.assertTrue(cp.is_supplier)
        self.assertFalse(cp.is_customer)
        self.assertEqual(cp.bank_accounts, [{"bank": "Kaspi", "account": "KZ001"}])
 
    def test_sync_updates_existing_counterparty(self):
        Counterparty.objects.create(
            id_1c="SYNC-001",
            full_name="Старое Имя",
            short_name="Старое",
            bin_number="100000000001",
        )
 
        updated = [{**MOCK_COUNTERPARTIES[0], "short_name": "Обновлённое"}]
        self._patch_client(return_value=updated)
 
        result = sync_counterparties()
 
        self.assertEqual(Counterparty.objects.count(), 1)          
        cp = Counterparty.objects.get(id_1c="SYNC-001")
        self.assertEqual(cp.short_name, "Обновлённое")            
        self.assertIn("обновлено 1", result)
        self.assertIn("создано 0", result)
 
    def test_sync_does_not_duplicate_on_repeated_calls(self):
        self._patch_client(return_value=MOCK_COUNTERPARTIES)
 
        sync_counterparties()
        sync_counterparties()
        sync_counterparties()
 
        self.assertEqual(Counterparty.objects.count(), 2)
 
 
    def test_synced_at_set_on_create(self):
        self._patch_client(return_value=MOCK_COUNTERPARTIES[:1])
 
        before = timezone.now()
        sync_counterparties()
        after = timezone.now()
 
        cp = Counterparty.objects.get(id_1c="SYNC-001")
        self.assertIsNotNone(cp.synced_at)
        self.assertGreaterEqual(cp.synced_at, before)
        self.assertLessEqual(cp.synced_at, after)
 
    def test_synced_at_updated_on_resync(self):
        Counterparty.objects.create(
            id_1c="SYNC-001",
            full_name="ТОО Первая Компания",
            short_name="Первая",
            bin_number="100000000001",
            synced_at=timezone.now() - timedelta(hours=5),  
        )
 
        self._patch_client(return_value=MOCK_COUNTERPARTIES[:1])
 
        old_ts = Counterparty.objects.get(id_1c="SYNC-001").synced_at
        sync_counterparties()
        new_ts = Counterparty.objects.get(id_1c="SYNC-001").synced_at
 
        self.assertGreater(new_ts, old_ts)

 
    def test_sync_handles_connection_error_gracefully(self):
        self._patch_client(side_effect=ConnectionError("1С недоступна"))
 
        result = sync_counterparties()
 
        self.assertIn("Сбой синхронизации", result)
        self.assertIn("1С недоступна", result)
        self.assertEqual(Counterparty.objects.count(), 0)
 
    def test_sync_handles_generic_exception_gracefully(self):
        self._patch_client(side_effect=RuntimeError("Неожиданная ошибка"))
 
        result = sync_counterparties()
 
        self.assertIn("Сбой синхронизации", result)
        self.assertEqual(Counterparty.objects.count(), 0)
 
    def test_sync_logs_error_on_failure(self):
        self._patch_client(side_effect=Exception("Ошибка подключения"))
 
        with self.assertLogs("onec.tasks", level="ERROR") as log_ctx:
            sync_counterparties()
 
        self.assertTrue(
            any("Сбой синхронизации" in msg for msg in log_ctx.output)
        )
 
 
    def test_sync_skips_items_without_id_1c(self):
        data = [
            {"id_1c": "", "full_name": "Без ID", "short_name": "БезID"},
            {"full_name": "Совсем без ключа", "short_name": "NoKey"},
            MOCK_COUNTERPARTIES[0],
        ]
        self._patch_client(return_value=data)
 
        sync_counterparties()
 
        self.assertEqual(Counterparty.objects.count(), 1)
        self.assertEqual(Counterparty.objects.first().id_1c, "SYNC-001")
 
    def test_sync_returns_no_data_when_empty_list(self):
        self._patch_client(return_value=[])
 
        result = sync_counterparties()
 
        self.assertEqual(result, "No data received")
        self.assertEqual(Counterparty.objects.count(), 0)
 
    def test_sync_logs_warning_when_no_data(self):
        self._patch_client(return_value=[])
 
        with self.assertLogs("onec.tasks", level="WARNING") as log_ctx:
            sync_counterparties()
 
        self.assertTrue(
            any("не получены" in msg for msg in log_ctx.output)
        )
