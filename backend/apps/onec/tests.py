from django.test import TestCase, override_settings, RequestFactory
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
from django.contrib.auth import get_user_model
from account.models import Department
from onec.models import Counterparty, CounterpartyType, AccessScope
from account.services.access_scope import get_visible_counterparties

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
        from account.models import UserAccount
        from account.role_permissions import RoleEnums
        self.user = UserAccount.objects.create_user(
            username='onec_view_user',
            password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.client.force_login(self.user)
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

    def test_invoice_create_get_page(self):
        url = reverse('onec:invoice_create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Новый счёт")

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
        from account.models import UserAccount
        from account.role_permissions import RoleEnums
        self.api_user = UserAccount.objects.create_user(
            username='onec_api_user',
            password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.client.force_authenticate(user=self.api_user)
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
        results = response.data.get('results', response.data)
        self.assertEqual(results[0]['short_name'], "API Test Company")
        self.assertIn('bank_accounts', results[0])

    def test_post_counterparty_fails(self):
        data = {"short_name": "New Comp", "bin_number": "000"}
        response = self.client.post(self.cp_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_get_invoices_nested(self):
        inv = Invoice.objects.create(counterparty=self.cp, number="INV-100")
        InvoiceItem.objects.create(invoice=inv, name="Item 1", quantity=1, price=100)
        
        response = self.client.get(self.invoice_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results[0]['items']), 1)
        self.assertEqual(results[0]['items'][0]['name'], "Item 1")

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
 
 
@override_settings(
    ONE_C_BASE_URL='https://1c.example/api/v1',
    ONE_C_API_USER='u',
    ONE_C_API_PASSWORD='p',
    ONE_C_BASIC_AUTH_USER='b',
    ONE_C_BASIC_AUTH_PASSWORD='b',
)
class SyncCounterpartiesTaskTest(TestCase):
    def _patch_client(self, return_value=None, side_effect=None):
        patcher = patch('onec.services.sync_counterparties.get_onec_client')
        mock_get = patcher.start()
        mock_instance = MagicMock()
        mock_get.return_value = mock_instance

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
 
        result = sync_counterparties()
        self.assertIn('Сбой синхронизации', result)
        self.assertIn('Ошибка подключения', result)
 
 
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

        result = sync_counterparties()
        self.assertEqual(result, 'No data received')


# ─── COLLAB-2: 1С integration smoke-test ──────────────────────────────────────

import copy
from django.conf import settings as django_settings
from django.test import Client, override_settings
from account.models import UserAccount
from account.role_permissions import RoleEnums

_COLLAB_ONEC_TEMPLATES = copy.deepcopy(django_settings.TEMPLATES)
_COLLAB_ONEC_TEMPLATES[0]['OPTIONS']['context_processors'] = [
    'django.template.context_processors.request',
    'django.contrib.auth.context_processors.auth',
    'django.contrib.messages.context_processors.messages',
]


@override_settings(
    ALLOWED_HOSTS=['testserver'],
    TEMPLATES=_COLLAB_ONEC_TEMPLATES,
    ONE_C_BASE_URL='https://1c.example/api/v1',
    ONE_C_API_USER='u',
    ONE_C_API_PASSWORD='p',
    ONE_C_BASIC_AUTH_USER='b',
    ONE_C_BASIC_AUTH_PASSWORD='b',
)
class OneCCollabSmokeTest(TestCase):
    """Smoke-test 1С UI, Select2 API и устойчивость sync (COLLAB-2)."""

    def setUp(self):
        self.user = UserAccount.objects.create_user(
            username='collab_onec',
            password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.cp = Counterparty.objects.create(
            id_1c='COLLAB-CP-01',
            full_name='Collab Counterparty LLP',
            short_name='Collab CP',
            bin_number='111122223333',
        )

    def test_counterparty_list_and_detail_screens(self):
        for name, kwargs in (
            ('onec:counterparty_list', {}),
            ('onec:counterparty_detail', {'pk': self.cp.pk}),
        ):
            with self.subTest(screen=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Collab CP')

    def test_counterparty_search_api_select2_format(self):
        response = self.client.get(reverse('onec:counterparty_search_api'), {'q': 'Collab'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('results', payload)
        self.assertTrue(payload['results'])
        self.assertIn('id', payload['results'][0])
        self.assertIn('text', payload['results'][0])

    def test_invoice_create_form_has_counterparty_select(self):
        response = self.client.get(reverse('onec:invoice_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cp_select')
        self.assertContains(response, 'item_name[]')

    def test_invoice_create_dynamic_line_items_post(self):
        post_data = {
            'counterparty': self.cp.id,
            'comment': 'COLLAB invoice',
            'item_name[]': ['Услуга A', 'Услуга B'],
            'item_qty[]': ['2', '1'],
            'item_price[]': ['1500', '3000'],
        }
        response = self.client.post(reverse('onec:invoice_create'), post_data)
        self.assertEqual(response.status_code, 302)
        invoice = Invoice.objects.filter(comment='COLLAB invoice').first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.items.count(), 2)

    def test_sync_survives_onec_unavailable(self):
        with patch('onec.services.sync_counterparties.get_onec_client') as mock_get:
            mock_get.return_value.get_counterparties.side_effect = ConnectionError('1С недоступна')
            result = sync_counterparties()
        self.assertIn('Сбой синхронизации', result)
        self.assertEqual(Counterparty.objects.filter(id_1c='COLLAB-CP-01').count(), 1)


User = get_user_model()


def make_user(username, role):
    return User.objects.create_user(
        username=username,
        password='test',
        role=role,
    )


def make_counterparty(short_name, bin_number):
    return Counterparty.objects.create(
        id_1c=f'1c_{bin_number}',
        full_name=short_name,
        short_name=short_name,
        bin_number=bin_number,
    )


class CounterpartyTypeTest(TestCase):
    def test_create_type(self):
        ct = CounterpartyType.objects.create(name='Поставщик', code='supplier')
        self.assertEqual(str(ct), 'Поставщик')


class AccessScopeTest(TestCase):
    def setUp(self):
        self.cp1 = make_counterparty('Компания А', '111111111111')
        self.cp2 = make_counterparty('Компания Б', '222222222222')
        self.cp3 = make_counterparty('Компания В', '333333333333')

    def test_admin_sees_all(self):
        user = make_user('admin1', 'administrator')
        qs = get_visible_counterparties(user)
        self.assertEqual(qs.count(), 3)

    def test_owner_sees_all(self):
        user = make_user('owner1', 'owner')
        qs = get_visible_counterparties(user)
        self.assertEqual(qs.count(), 3)

    def test_cfo_sees_all(self):
        user = make_user('cfo1', 'cfo')
        qs = get_visible_counterparties(user)
        self.assertEqual(qs.count(), 3)

    def test_chief_accountant_sees_all(self):
        user = make_user('ca1', 'chief_accountant')
        qs = get_visible_counterparties(user)
        self.assertEqual(qs.count(), 3)

    def test_staff_no_scope_sees_all(self):
        user = make_user('staff1', 'staff')
        qs = get_visible_counterparties(user)
        self.assertEqual(qs.count(), 3)

    def test_staff_with_scope_sees_only_assigned(self):
        user = make_user('staff2', 'staff')
        scope = AccessScope.objects.create(name='Тест скоп')
        scope.users.add(user)
        scope.counterparties.add(self.cp1, self.cp2)

        qs = get_visible_counterparties(user)
        self.assertEqual(qs.count(), 2)
        self.assertIn(self.cp1, qs)
        self.assertIn(self.cp2, qs)
        self.assertNotIn(self.cp3, qs)

    def test_counterparty_type_fk(self):
        ct = CounterpartyType.objects.create(name='Клиент', code='client')
        self.cp1.counterparty_type = ct
        self.cp1.save()
        self.assertEqual(self.cp1.counterparty_type.code, 'client')