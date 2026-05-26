from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount
from account.role_permissions import RoleEnums
from documents.enums import DocumentTypeEnum
from documents.folder_structure import ensure_folder_tree
from documents.models import Document, Folder
from documents.services import documents_list
from django.test import RequestFactory


class FolderStructureTests(TestCase):
    def test_ensure_purchase_folders(self):
        root = ensure_folder_tree(DocumentTypeEnum.PURCHASES.value[0])
        descendants = root.get_descendants(include_self=False)
        self.assertGreaterEqual(descendants.count(), 5)
        self.assertTrue(
            Folder.objects.filter(name='Закупки / Заявки на закупку').exists()
        )

    def test_get_by_root_type_returns_leaf_folders(self):
        ensure_folder_tree(DocumentTypeEnum.PURCHASES.value[0])
        qs = Folder.get_by_root_type(DocumentTypeEnum.PURCHASES.value[0])
        self.assertGreaterEqual(qs.count(), 5)

    def test_folder_list_filters_by_subtree(self):
        root = ensure_folder_tree(DocumentTypeEnum.PURCHASES.value[0])
        leaf = Folder.objects.get(name='Закупки / Договоры с поставщиками')
        user = UserAccount.objects.create_user(
            username='folder_user',
            password='testpass123',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        doc = Document.objects.create(
            document_type=DocumentTypeEnum.PURCHASES.value[0],
            folder=leaf,
            author=user,
            status='draft',
            title='Договор поставки',
            number='Z-001',
            supplier=None,
        )
        doc.coordinators.add(user)
        doc.observers.add(user)

        factory = RequestFactory()
        request = factory.get(f'/doc/purchases/folder/{leaf.id}/')
        request.user = user

        response = documents_list(
            request,
            DocumentTypeEnum.PURCHASES.value[0],
            folder=leaf.id,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Z-001')
        self.assertContains(response, 'Договор поставки')

    def test_purchases_list_page_has_folder_links(self):
        ensure_folder_tree(DocumentTypeEnum.PURCHASES.value[0])
        user = UserAccount.objects.create_user(
            username='nav_user',
            password='testpass123',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.client.force_login(user)
        url = reverse('documents:list', kwargs={'document_type': 'purchases'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Заявки на закупку')
        leaf = Folder.objects.get(name='Закупки / Заявки на закупку')
        self.assertContains(
            response,
            reverse('documents:by_folder', kwargs={'document_type': 'purchases', 'folder': leaf.id}),
        )
