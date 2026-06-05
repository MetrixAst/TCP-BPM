from django.test import TestCase
from account.models import UserAccount
from account.role_permissions import RoleEnums, RolePermissions, PermissionEnums
from requistions.enums import RequstionTypesEnum
from tenants.models import Tenant


class TenantRoleTest(TestCase):

    def setUp(self):
        self.tenant_obj = Tenant.objects.create(name='TestTenant', area=0, price=0)
        self.tenant_user = UserAccount.objects.create_user(
            username='tenant_test', password='pass', role=RoleEnums.TENANT.value
        )
        self.tenant_user.tenant = self.tenant_obj
        self.tenant_user.save()

    def test_tenant_role_exists(self):
        self.assertEqual(RoleEnums.TENANT.value, 'tenant')

    def test_tenant_has_requistions_permission(self):
        self.assertTrue(
            RolePermissions.checkPermission(
                RoleEnums.TENANT.value, PermissionEnums.REQUISTIONS
            )
        )

    def test_tenant_has_no_hr_permission(self):
        self.assertFalse(
            RolePermissions.checkPermission(
                RoleEnums.TENANT.value, PermissionEnums.HR
            )
        )

    def test_tenant_fk_on_user(self):
        self.assertEqual(self.tenant_user.tenant, self.tenant_obj)

    def test_new_requistion_types_exist(self):
        types = [t.value[0] for t in RequstionTypesEnum]
        self.assertIn('repair', types)
        self.assertIn('cleaning', types)
        self.assertIn('incident', types)
        self.assertIn('other', types)

    def test_notify_operations_creates_notifications(self):
        from account.models import Notification
        from requistions.models import Requistion
        from purchases.models import Supplier

        admin = UserAccount.objects.create_user(
            username='admin_fix07', password='pass', role=RoleEnums.ADMINISTRATOR.value
        )
        supplier = Supplier.objects.create(name='TestSupplier')
        req = Requistion.objects.create(
            requistion_type='repair',
            user=self.tenant_user,
            supplier=supplier,
            status='draft',
        )
        req.notify_operations()
        self.assertTrue(
            Notification.objects.filter(
                target_type='requistion',
                target_id=req.id,
                users=admin,
            ).exists()
        )