from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from account.models import AccessScope
from account.role_permissions import RoleEnums

from .enums import DocumentStatusEnum, DocumentTypeEnum
from .folder_structure import ensure_folder_tree
from .models import Document


User = get_user_model()


class DocumentVisibilityTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        root = ensure_folder_tree(DocumentTypeEnum.DOCUMENTS.value[0])
        self.folder = root.get_descendants(include_self=False).filter(lft=root.lft + 1).first()
        if self.folder is None:
            self.folder = root.get_descendants(include_self=False).first() or root

        self.hr = User.objects.create_user(
            username='hr_vis',
            password='x',
            role=RoleEnums.HR.value,
        )
        self.staff = User.objects.create_user(
            username='staff_vis',
            password='x',
            role=RoleEnums.STAFF.value,
        )
        self.admin = User.objects.create_user(
            username='admin_vis',
            password='x',
            role=RoleEnums.ADMINISTRATOR.value,
        )

        self.doc = Document.objects.create(
            document_type=DocumentTypeEnum.DOCUMENTS.value[0],
            folder=self.folder,
            author=self.hr,
            status=DocumentStatusEnum.DRAFT.value[0],
            title='HR doc',
            number='DOC-VIS-1',
        )
        # Как раньше при создании: только автор в участниках
        self.doc.coordinators.set([self.hr])
        self.doc.observers.set([self.hr])

    def _req(self, user):
        req = self.factory.get('/')
        req.user = user
        return req

    def test_open_docflow_visible_to_others_and_admin(self):
        # access_scope=None → виден всем с доступом к папке (и админу)
        qs_staff = Document.get_available_queryset(self._req(self.staff))
        qs_admin = Document.get_available_queryset(self._req(self.admin))
        self.assertTrue(qs_staff.filter(pk=self.doc.pk).exists())
        self.assertTrue(qs_admin.filter(pk=self.doc.pk).exists())

    def test_role_restricted_document(self):
        scope = AccessScope.objects.create(name='HR only docs', roles=[RoleEnums.HR.value])
        self.doc.access_scope = scope
        self.doc.save(update_fields=['access_scope'])

        qs_hr = Document.get_available_queryset(self._req(self.hr))
        qs_staff = Document.get_available_queryset(self._req(self.staff))
        qs_admin = Document.get_available_queryset(self._req(self.admin))

        self.assertTrue(qs_hr.filter(pk=self.doc.pk).exists())
        self.assertFalse(qs_staff.filter(pk=self.doc.pk).exists())
        self.assertTrue(qs_admin.filter(pk=self.doc.pk).exists())
