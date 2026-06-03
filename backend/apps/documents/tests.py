from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from documents.models import Folder
from onec.models import AccessScope
from documents.services.access_scope import get_visible_folders
from account.role_permissions import RoleEnums

UserAccount = get_user_model()


class FolderACLTest(TestCase):

    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            username='admin_test', password='pass', role=RoleEnums.ADMINISTRATOR.value
        )
        self.staff = UserAccount.objects.create_user(
            username='staff_test', password='pass', role=RoleEnums.STAFF.value
        )
        self.folder1 = Folder.objects.create(name='Folder1')
        self.folder2 = Folder.objects.create(name='Folder2')

    def test_admin_sees_all_folders(self):
        qs = get_visible_folders(self.admin)
        self.assertIn(self.folder1, qs)
        self.assertIn(self.folder2, qs)

    def test_staff_without_scope_sees_all(self):
        qs = get_visible_folders(self.staff)
        self.assertIn(self.folder1, qs)
        self.assertIn(self.folder2, qs)

    def test_staff_with_scope_sees_only_assigned(self):
        scope = AccessScope.objects.create(name='Test scope')
        scope.users.add(self.staff)
        scope.folders.add(self.folder1)

        qs = get_visible_folders(self.staff)
        self.assertIn(self.folder1, qs)
        self.assertNotIn(self.folder2, qs)