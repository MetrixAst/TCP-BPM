from io import BytesIO

import openpyxl
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount
from purchases.models import Supplier
from .models import Tenant


def xlsx(rows):
    wb = openpyxl.Workbook()
    for row in rows:
        wb.active.append(row)
    buffer = BytesIO()
    wb.save(buffer)
    return SimpleUploadedFile('import.xlsx', buffer.getvalue())


class ExcelImportTest(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = UserAccount.objects.create_user(username='admin_imp', password='pass', role='administrator')
        self.client.force_login(self.admin)

    def test_template_download(self):
        response = self.client.get(reverse('tenants:import') + '?template=1')
        wb = openpyxl.load_workbook(BytesIO(response.content))
        self.assertEqual(wb.active['A1'].value, 'Название')

    def test_tenants_created_and_updated(self):
        Tenant.objects.create(name='Аптека', area=10, price=1, phone='', email='', address='', contact='')
        upload = xlsx([
            ['Название', 'Помещение', 'Площадь', 'Ставка за м2', 'Окончание аренды'],
            ['Аптека', 'B-2', 20, 3000, '31.12.2026'],
            ['Книжный', 'B-3', '15,5', 2500, None],
        ])
        response = self.client.post(reverse('tenants:import'), {'file': upload})
        self.assertRedirects(response, reverse('tenants:list'))
        self.assertEqual(Tenant.objects.count(), 2)
        pharmacy = Tenant.objects.get(name='Аптека')
        self.assertEqual(pharmacy.area, 20)
        self.assertEqual(pharmacy.room.number, 'B-2')
        self.assertEqual(Tenant.objects.get(name='Книжный').area, 15.5)

    def test_errors_block_whole_file(self):
        upload = xlsx([
            ['Название', 'Площадь', 'Ставка за м2'],
            ['Хорошая строка', 10, 100],
            ['', 'много', 100],
        ])
        response = self.client.post(reverse('tenants:import'), {'file': upload})
        self.assertEqual(response.status_code, 200)
        rows = {row for row, _text in response.context['result'].errors}
        self.assertEqual(rows, {3})
        self.assertFalse(Tenant.objects.exists())

    def test_suppliers_import_matches_by_bin(self):
        Supplier.objects.create(name='Старое имя', identifier='123456789012', status='checked', address2='-')
        upload = xlsx([
            ['Наименование', 'БИН/ИИН', 'Телефон'],
            ['ТОО Ромашка', '123456789012', '+7 701'],
            ['ИП Сидоров', '', ''],
        ])
        response = self.client.post(reverse('purchases:import_suppliers'), {'file': upload})
        self.assertRedirects(response, reverse('purchases:suppliers'), fetch_redirect_response=False)
        self.assertEqual(Supplier.objects.count(), 2)
        updated = Supplier.objects.get(identifier='123456789012')
        self.assertEqual(updated.name, 'ТОО Ромашка')
        self.assertEqual(updated.status, 'checked')
