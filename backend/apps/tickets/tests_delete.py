import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from account.models import UserAccount
from tickets.models import ServiceRequest, TicketAttachment, TicketMessage

MEDIA = tempfile.mkdtemp()


def make_user(username, role='staff', **extra):
    return UserAccount.objects.create_user(username=username, password='pass', role=role, **extra)


def make_ticket(author, status='new', category='other'):
    return ServiceRequest.objects.create(
        author=author, title='Тест удаления', category=category, priority='medium', status=status,
    )


@override_settings(MEDIA_ROOT=MEDIA)
class TicketDeleteTest(TestCase):

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.admin = make_user('admin_del', role='administrator')
        self.client.force_login(self.admin)

    def test_delete_one_removes_ticket_children_and_files(self):
        ticket = make_ticket(self.admin)
        TicketMessage.objects.create(request=ticket, author=self.admin, text='привет')
        att = TicketAttachment.objects.create(
            request=ticket, file=SimpleUploadedFile('a.txt', b'data'), original_name='a.txt',
        )
        storage, path = att.file.storage, att.file.name
        self.assertTrue(storage.exists(path))

        resp = self.client.post(reverse('tickets:delete_one', args=[ticket.pk]))

        self.assertRedirects(resp, reverse('tickets:home'), fetch_redirect_response=False)
        self.assertFalse(ServiceRequest.objects.filter(pk=ticket.pk).exists())
        self.assertFalse(TicketMessage.objects.exists())
        self.assertFalse(TicketAttachment.objects.exists())
        self.assertFalse(storage.exists(path))

    def test_delete_one_requires_post(self):
        ticket = make_ticket(self.admin)
        resp = self.client.get(reverse('tickets:delete_one', args=[ticket.pk]))
        self.assertEqual(resp.status_code, 405)
        self.assertTrue(ServiceRequest.objects.filter(pk=ticket.pk).exists())

    def test_bulk_delete_all(self):
        for _ in range(3):
            make_ticket(self.admin)
        self.client.post(reverse('tickets:delete_bulk'), {'scope': 'all', 'confirm': 'удалить'})
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_bulk_delete_requires_confirm_word(self):
        make_ticket(self.admin)
        self.client.post(reverse('tickets:delete_bulk'), {'scope': 'all', 'confirm': 'да'})
        self.assertEqual(ServiceRequest.objects.count(), 1)

    def test_bulk_delete_filtered_keeps_others(self):
        make_ticket(self.admin, status='new')
        make_ticket(self.admin, status='new')
        keep = make_ticket(self.admin, status='done')
        self.client.post(reverse('tickets:delete_bulk'), {
            'scope': 'filtered', 'status': 'new', 'category': '', 'confirm': 'УДАЛИТЬ',
        })
        self.assertEqual(list(ServiceRequest.objects.values_list('pk', flat=True)), [keep.pk])

    def test_superuser_can_delete(self):
        su = make_user('su_del', role='staff', is_superuser=True, is_staff=True)
        self.client.force_login(su)
        ticket = make_ticket(su)
        self.client.post(reverse('tickets:delete_one', args=[ticket.pk]))
        self.assertFalse(ServiceRequest.objects.filter(pk=ticket.pk).exists())

    def test_ticket_card_has_delete_button(self):
        ticket = make_ticket(self.admin)
        resp = self.client.get(reverse('tickets:item', args=[ticket.pk]))
        self.assertContains(resp, reverse('tickets:delete_one', args=[ticket.pk]))

    def test_list_shows_delete_button_only_for_admin(self):
        make_ticket(self.admin)
        resp = self.client.get(reverse('tickets:home'))
        self.assertContains(resp, 'tkDeleteDialog')

        hr = make_user('hr_del', role='hr')
        self.client.force_login(hr)
        resp = self.client.get(reverse('tickets:home'))
        self.assertNotContains(resp, 'tkDeleteDialog', status_code=resp.status_code)


class TicketDeleteForbiddenTest(TestCase):

    def test_non_admin_roles_cannot_delete(self):
        author = make_user('author_del', role='administrator')
        ticket = make_ticket(author)
        for role in ('staff', 'hr', 'owner', 'cfo', 'tenant'):
            user = make_user(f'{role}_nodel', role=role)
            self.client.force_login(user)
            self.client.post(reverse('tickets:delete_one', args=[ticket.pk]))
            self.client.post(reverse('tickets:delete_bulk'), {'scope': 'all', 'confirm': 'УДАЛИТЬ'})
            self.assertTrue(ServiceRequest.objects.filter(pk=ticket.pk).exists(), role)
