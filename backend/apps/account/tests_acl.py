from django.test import TestCase

from account.models import AccessScope, UserAccount
from account.role_permissions import RoleEnums
from account.services.access_scope import (
    filter_counterparties_queryset,
    filter_suppliers_queryset,
    user_can_view_counterparty,
    user_can_view_supplier,
)
from onec.models import Counterparty, CounterpartyType
from purchases.models import Supplier


class CounterpartyAclMatrixTestCase(TestCase):
    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            username='acl_admin', password='pass', role=RoleEnums.ADMINISTRATOR.value,
        )
        self.hr_user = UserAccount.objects.create_user(
            username='acl_hr', password='pass', role=RoleEnums.HR.value,
        )
        self.staff_user = UserAccount.objects.create_user(
            username='acl_staff', password='pass', role=RoleEnums.STAFF.value,
        )

        self.hr_scope = AccessScope.objects.create(
            name='HR scope', is_global=False, roles=[RoleEnums.HR.value],
        )
        self.global_scope = AccessScope.objects.create(name='Global scope', is_global=True)

        self.hr_only_type = CounterpartyType.objects.create(
            name='HR only', code='hr_only', access_scope=self.hr_scope, is_active=True,
        )
        self.global_type = CounterpartyType.objects.create(
            name='Global type', code='global_type', access_scope=self.global_scope, is_active=True,
        )
        self.no_scope_type = CounterpartyType.objects.create(
            name='No scope type', code='no_scope', access_scope=None, is_active=True,
        )

        self.cp_hr = Counterparty.objects.create(
            id_1c='CP-HR', full_name='HR Counterparty', short_name='HR CP',
            counterparty_type=self.hr_only_type,
        )
        self.cp_global = Counterparty.objects.create(
            id_1c='CP-GLOBAL', full_name='Global Counterparty', short_name='Global CP',
            counterparty_type=self.global_type,
        )
        self.cp_no_type = Counterparty.objects.create(
            id_1c='CP-NONE', full_name='No Type Counterparty', short_name='No Type CP',
            counterparty_type=None,
        )

    def test_admin_sees_everything(self):
        qs = filter_counterparties_queryset(Counterparty.objects.all(), self.admin)
        self.assertIn(self.cp_hr, qs)
        self.assertIn(self.cp_global, qs)
        self.assertIn(self.cp_no_type, qs)

    def test_hr_user_sees_hr_and_global_and_untyped(self):
        qs = filter_counterparties_queryset(Counterparty.objects.all(), self.hr_user)
        self.assertIn(self.cp_hr, qs)
        self.assertIn(self.cp_global, qs)
        self.assertIn(self.cp_no_type, qs)

    def test_staff_user_sees_only_global_and_untyped(self):
        qs = filter_counterparties_queryset(Counterparty.objects.all(), self.staff_user)
        self.assertNotIn(self.cp_hr, qs)
        self.assertIn(self.cp_global, qs)
        self.assertIn(self.cp_no_type, qs)

    def test_user_can_view_counterparty_matches_queryset(self):
        self.assertTrue(user_can_view_counterparty(self.hr_user, self.cp_hr))
        self.assertFalse(user_can_view_counterparty(self.staff_user, self.cp_hr))
        self.assertTrue(user_can_view_counterparty(self.staff_user, self.cp_global))
        self.assertTrue(user_can_view_counterparty(self.staff_user, self.cp_no_type))


class SupplierAclMatrixTestCase(TestCase):
    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            username='acl_sup_admin', password='pass', role=RoleEnums.ADMINISTRATOR.value,
        )
        self.hr_user = UserAccount.objects.create_user(
            username='acl_sup_hr', password='pass', role=RoleEnums.HR.value,
        )
        self.staff_user = UserAccount.objects.create_user(
            username='acl_sup_staff', password='pass', role=RoleEnums.STAFF.value,
        )

        self.hr_scope = AccessScope.objects.create(
            name='Supplier HR scope', is_global=False, roles=[RoleEnums.HR.value],
        )
        self.hr_only_type = CounterpartyType.objects.create(
            name='Supplier HR only', code='sup_hr_only', access_scope=self.hr_scope, is_active=True,
        )

        self.cp_hr = Counterparty.objects.create(
            id_1c='SUP-CP-HR', full_name='HR Linked Counterparty', short_name='HR Linked',
            counterparty_type=self.hr_only_type,
        )

        self.supplier_linked = Supplier.objects.create(
            name='Linked supplier', onec_id='SUP-CP-HR',
        )
        self.supplier_unlinked = Supplier.objects.create(
            name='Unlinked supplier', onec_id='',
        )
        self.supplier_orphan = Supplier.objects.create(
            name='Orphan supplier', onec_id='NON-EXISTENT-ID',
        )

    def test_admin_sees_all_suppliers(self):
        qs = filter_suppliers_queryset(Supplier.objects.all(), self.admin)
        self.assertIn(self.supplier_linked, qs)
        self.assertIn(self.supplier_unlinked, qs)
        self.assertIn(self.supplier_orphan, qs)

    def test_hr_sees_linked_supplier(self):
        qs = filter_suppliers_queryset(Supplier.objects.all(), self.hr_user)
        self.assertIn(self.supplier_linked, qs)

    def test_staff_does_not_see_restricted_linked_supplier(self):
        qs = filter_suppliers_queryset(Supplier.objects.all(), self.staff_user)
        self.assertNotIn(self.supplier_linked, qs)

    def test_unlinked_supplier_visible_to_everyone(self):
        qs_staff = filter_suppliers_queryset(Supplier.objects.all(), self.staff_user)
        self.assertIn(self.supplier_unlinked, qs_staff)

    def test_orphan_supplier_visible_when_counterparty_missing(self):
        qs_staff = filter_suppliers_queryset(Supplier.objects.all(), self.staff_user)
        self.assertIn(self.supplier_orphan, qs_staff)

    def test_user_can_view_supplier_matches_queryset(self):
        self.assertTrue(user_can_view_supplier(self.hr_user, self.supplier_linked))
        self.assertFalse(user_can_view_supplier(self.staff_user, self.supplier_linked))
        self.assertTrue(user_can_view_supplier(self.staff_user, self.supplier_unlinked))
        self.assertTrue(user_can_view_supplier(self.staff_user, self.supplier_orphan))