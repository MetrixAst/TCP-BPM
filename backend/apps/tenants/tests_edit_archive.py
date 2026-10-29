from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from account.models import UserAccount
from purchases.enums import SupplierStatusEnum
from purchases.models import Supplier
from purchases.services.sync_from_onec import sync_counterparties_to_suppliers
from onec.models import Counterparty
from .models import Tenant


def make_tenant(**kwargs):
    data = {'name': 'Кофейня', 'area': 40, 'price': 5000, 'phone': '', 'email': 'a@b.kz', 'address': '', 'contact': ''}
    data.update(kwargs)
    return Tenant.objects.create(**data)


class TenantEditArchiveTest(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = UserAccount.objects.create_user(username='admin_ten', password='pass', role='administrator')
        self.staff = UserAccount.objects.create_user(username='staff_ten', password='pass', role='staff')
        self.tenant = make_tenant()

    def test_admin_edits_tenant(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('tenants:edit', args=[self.tenant.pk]), {
            'name': 'Кофейня Плюс', 'area': 55, 'price': 6000, 'room': 'A-12',
            'discount': 0, 'percent': 0, 'email': 'new@b.kz',
        })
        self.assertRedirects(response, reverse('tenants:detail', args=[self.tenant.pk]))
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.name, 'Кофейня Плюс')
        self.assertEqual(self.tenant.room.number, 'A-12')

    def test_edit_form_and_detail_render(self):
        self.client.force_login(self.admin)
        form = self.client.get(reverse('tenants:edit', args=[self.tenant.pk]))
        self.assertContains(form, 'Редактирование арендатора')
        detail = self.client.get(reverse('tenants:detail', args=[self.tenant.pk]))
        self.assertContains(detail, reverse('tenants:edit', args=[self.tenant.pk]))

    def test_staff_cannot_edit(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('tenants:edit', args=[self.tenant.pk]))
        self.assertEqual(response.status_code, 403)

    def test_archive_hides_from_list(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('tenants:archive', args=[self.tenant.pk]))
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.is_active)

        active = self.client.get(reverse('tenants:list'))
        self.assertNotIn(self.tenant, list(active.context['paginator'].items))
        archived = self.client.get(reverse('tenants:list') + '?archived=1')
        self.assertIn(self.tenant, list(archived.context['paginator'].items))

    def test_delete(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('tenants:delete', args=[self.tenant.pk]))
        self.assertRedirects(response, reverse('tenants:list'))
        self.assertFalse(Tenant.objects.filter(pk=self.tenant.pk).exists())


class SupplierSyncKeepsEditsTest(TestCase):
    def setUp(self):
        self.cp = Counterparty.objects.create(
            id_1c='cp-1', full_name='ТОО Ромашка', short_name='Ромашка', phone='+7 700',
        )

    def test_manual_edits_survive_sync(self):
        sync_counterparties_to_suppliers()
        supplier = Supplier.objects.get(onec_id='cp-1')
        supplier.name = 'Ромашка (исправлено)'
        supplier.status = SupplierStatusEnum.REFUSED.value[0]
        supplier.phone = None
        supplier.save()

        sync_counterparties_to_suppliers()
        supplier.refresh_from_db()
        self.assertEqual(supplier.name, 'Ромашка (исправлено)')
        self.assertEqual(supplier.status, SupplierStatusEnum.REFUSED.value[0])
        self.assertEqual(supplier.phone, '+7 700')

    def test_onec_supplier_cannot_be_deleted_only_archived(self):
        cache.clear()
        self.addCleanup(cache.clear)
        sync_counterparties_to_suppliers()
        supplier = Supplier.objects.get(onec_id='cp-1')
        admin = UserAccount.objects.create_user(username='admin_sup', password='pass', role='administrator')
        self.client.force_login(admin)

        self.client.post(reverse('purchases:delete_supplier', args=[supplier.pk]))
        self.assertTrue(Supplier.objects.filter(pk=supplier.pk).exists())

        self.client.post(reverse('purchases:archive_supplier', args=[supplier.pk]))
        supplier.refresh_from_db()
        self.assertFalse(supplier.is_active)


class TenantPortalAndSigningTest(TestCase):
    def setUp(self):
        self.admin = UserAccount.objects.create_user(username='boss_sign', password='pass', role='administrator')
        self.tenant = Tenant.objects.create(
            name='Аптека', area=10, price=1, phone='', email='apteka@example.com', address='', contact='',
        )
        self.client.force_login(self.admin)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_portal_password_hidden_when_emailed(self):
        from django.core import mail

        response = self.client.post(reverse('tenants:portal_access', args=[self.tenant.pk]), {'send_email': '1'})
        data = response.json()
        self.assertTrue(data['email_sent'])
        self.assertIsNone(data['password'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('apteka@example.com', mail.outbox[0].body)

    def test_document_sent_to_esigner(self):
        from unittest import mock
        from django.core.files.uploadedfile import SimpleUploadedFile
        from tenants.models import TenantDocument

        doc = TenantDocument.objects.create(
            tenant=self.tenant, title='АВР сентябрь', file=SimpleUploadedFile('avr.pdf', b'%PDF-1.4 test'),
        )
        signing = mock.Mock(sign_url='https://sign.example/abc')
        with mock.patch('esigner.services.send_for_signing', return_value=signing) as send:
            response = self.client.post(
                reverse('tenants:document_esign', args=[self.tenant.pk, doc.pk]),
                {'iin': '123456789012', 'is_company': 'on'},
            )
        self.assertRedirects(response, 'https://sign.example/abc', fetch_redirect_response=False)
        send.assert_called_once_with(doc, 'file', [{'bin_or_iin': '123456789012', 'is_company': True}])

        detail = self.client.get(reverse('tenants:detail', args=[self.tenant.pk]))
        self.assertContains(detail, 'Подписать ЭЦП')

    def test_document_esign_rejects_bad_iin(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from tenants.models import TenantDocument

        doc = TenantDocument.objects.create(
            tenant=self.tenant, title='Договор', file=SimpleUploadedFile('d.pdf', b'%PDF'),
        )
        response = self.client.post(
            reverse('tenants:document_esign', args=[self.tenant.pk, doc.pk]), {'iin': '12'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].endswith('#docs'))
