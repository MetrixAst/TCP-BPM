from django.test import TestCase
from django.urls import reverse

from account.models import AccessScope, Department, Employee, UserAccount
from account.role_permissions import RoleEnums
from account.services.access_scope import get_visible_folder_tree_nodes, user_can_view_folder
from documents.enums import DocumentTypeEnum
from documents.folder_structure import ensure_folder_tree
from documents.models import Document, Folder
from hr.enums import EmployeeStatusEnum
from hr.models import Company, Position


class FolderAccessScopeTest(TestCase):
    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            username='docs_acl_admin',
            password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.staff = UserAccount.objects.create_user(
            username='docs_acl_staff',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        company = Company.objects.create(name='Docs Co')
        department = Department.objects.create(name='Legal', company=company)
        position = Position.objects.create(title='Lawyer', department=department)
        Employee.objects.create(
            user=self.staff,
            department=department,
            position=position,
            status=EmployeeStatusEnum.ACTIVE,
        )

        self.root = ensure_folder_tree(DocumentTypeEnum.DOCUMENTS.value[0])
        self.public_folder = Folder.objects.filter(
            tree_id=self.root.tree_id,
            lft=self.root.lft + 1,
        ).first() or self.root

        scope = AccessScope.objects.create(name='Legal docs', roles=[RoleEnums.STAFF.value])
        scope.departments.add(department)
        self.restricted_folder = Folder.objects.create(
            name='ACL / Restricted',
            parent=self.root,
            access_scope=scope,
        )
        self.hidden_folder = Folder.objects.create(
            name='ACL / HR only',
            parent=self.root,
            access_scope=AccessScope.objects.create(name='HR only', roles=[RoleEnums.HR.value]),
        )

    def test_staff_sees_public_branch_in_tree(self):
        tree = get_visible_folder_tree_nodes(self.staff, self.root, include_self=False)
        names = list(tree.values_list('name', flat=True))
        self.assertIn(self.restricted_folder.name, names)
        self.assertNotIn(self.hidden_folder.name, names)

    def test_staff_cannot_open_hidden_folder_list(self):
        self.assertTrue(self.client.login(username='docs_acl_staff', password='pass'))
        url = reverse(
            'documents:by_folder',
            kwargs={
                'document_type': DocumentTypeEnum.DOCUMENTS.value[0],
                'folder': self.hidden_folder.pk,
            },
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_folder_settings_requires_admin(self):
        self.assertTrue(self.client.login(username='docs_acl_staff', password='pass'))
        url = reverse(
            'documents:folder_access_list',
            kwargs={'document_type': DocumentTypeEnum.DOCUMENTS.value[0]},
        )
        self.assertEqual(self.client.get(url).status_code, 403)
