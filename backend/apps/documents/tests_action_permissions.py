from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from account.models_rbac import AppPermission, UserPermissionOverride
from account.role_permissions import RoleEnums

from .enums import DocumentStatusEnum, DocumentTypeEnum
from .folder_structure import ensure_folder_tree
from .models import Document

User = get_user_model()
S = DocumentStatusEnum


class DocumentActionPermissionTests(TestCase):
    """Согласование, подписание и удаление документов проверяют права."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        root = ensure_folder_tree(DocumentTypeEnum.DOCUMENTS.value[0])
        folder = root.get_descendants(include_self=False).first() or root

        def user(name, role=RoleEnums.STAFF.value):
            return User.objects.create_user(username=name, password='x', role=role)

        self.author = user('doc_author')
        self.coordinator = user('doc_coord')
        self.outsider = user('doc_outsider')
        self.doc = Document.objects.create(
            document_type=DocumentTypeEnum.DOCUMENTS.value[0], folder=folder, author=self.author,
            status=S.DRAFT.value[0], title='Договор', number='DOC-ACT-1',
        )
        self.doc.coordinators.set([self.coordinator])

    def _grant(self, user, code):
        UserPermissionOverride.objects.create(
            user=user, permission=AppPermission.objects.get(code=code), effect='ALLOW',
        )
        cache.clear()

    def _post(self, user, action):
        self.client.force_login(user)
        return self.client.post(reverse('documents:document_action', args=[self.doc.pk]), {'action': action})

    def _status(self):
        self.doc.refresh_from_db()
        return self.doc.status

    def test_outsider_cannot_delete_or_move(self):
        self.assertEqual(self._post(self.outsider, 'cancel').status_code, 403)
        self.assertEqual(self._post(self.outsider, 'confirm').status_code, 403)
        self.assertTrue(Document.objects.filter(pk=self.doc.pk).exists())
        self.assertEqual(self._status(), S.DRAFT.value[0])

    def test_author_sends_to_coordination_and_coordinator_approves(self):
        self._post(self.author, 'confirm')
        self.assertEqual(self._status(), S.COORDINATION.value[0])

        self.assertEqual(self._post(self.author, 'confirm').status_code, 403)
        self._post(self.coordinator, 'confirm')
        self.assertEqual(self._status(), S.SIGNING.value[0])

    def test_signing_requires_sign_permission(self):
        Document.objects.filter(pk=self.doc.pk).update(status=S.SIGNING.value[0])
        self.assertEqual(self._post(self.coordinator, 'confirm').status_code, 403)

        self._grant(self.coordinator, 'documents_sign')
        self._post(self.coordinator, 'confirm')
        self.assertEqual(self._status(), S.ACTIVE.value[0])

    def test_approve_any_permission(self):
        Document.objects.filter(pk=self.doc.pk).update(status=S.COORDINATION.value[0])
        self._grant(self.outsider, 'documents_approve')
        self._post(self.outsider, 'confirm')
        self.assertEqual(self._status(), S.SIGNING.value[0])

    def test_delete_any_permission(self):
        Document.objects.filter(pk=self.doc.pk).update(status=S.ACTIVE.value[0])
        self._grant(self.outsider, 'documents_delete')
        self._post(self.outsider, 'cancel')
        self.assertFalse(Document.objects.filter(pk=self.doc.pk).exists())

    def test_get_does_not_change_anything(self):
        self.client.force_login(self.author)
        self.client.get(reverse('documents:document_action', args=[self.doc.pk]), {'action': 'cancel'})
        self.assertTrue(Document.objects.filter(pk=self.doc.pk).exists())
