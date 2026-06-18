"""Проверка зон видимости (AccessScope) для контрагентов и др."""

from django.db.models import F, Q

from account.models import AccessScope
from account.role_permissions import RoleEnums


FULL_ACCESS_ROLES = {
    RoleEnums.ADMINISTRATOR.value,
}


def user_has_full_access(user) -> bool:
    """Полный доступ к сущностям с AccessScope (контрагенты, папки и т.д.)."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'role', None) in FULL_ACCESS_ROLES


def user_has_full_counterparty_access(user) -> bool:
    return user_has_full_access(user)


def user_can_manage_access_scopes(user) -> bool:
    return user_has_full_access(user)


def user_has_full_folder_access(user) -> bool:
    return user_has_full_access(user)


def user_can_view_folder(user, folder) -> bool:
    if user_has_full_folder_access(user):
        return True
    if not folder.access_scope_id:
        return True
    return access_scope_matches_user(folder.access_scope, user)


def filter_folders_queryset(queryset, user):
    if user_has_full_folder_access(user):
        return queryset
    allowed_ids = [
        folder.pk
        for folder in queryset.select_related('access_scope')
        if user_can_view_folder(user, folder)
    ]
    return queryset.filter(pk__in=allowed_ids)


def get_visible_folder_tree_nodes(user, root, include_self=False):
    """Папки для сайдбара: видимые узлы + предки, чтобы дерево не рвалось."""
    all_nodes = root.get_descendants(include_self=include_self)
    if user_has_full_folder_access(user):
        return all_nodes

    visible_pks = set()
    nodes = list(all_nodes.select_related('access_scope'))
    by_pk = {node.pk: node for node in nodes}

    for node in nodes:
        if not user_can_view_folder(user, node):
            continue
        visible_pks.add(node.pk)
        parent_id = node.parent_id
        while parent_id and parent_id in by_pk:
            visible_pks.add(parent_id)
            parent_id = by_pk[parent_id].parent_id

    return all_nodes.filter(pk__in=visible_pks)


def get_assignable_folders(user, document_type):
    """Листовые папки, куда можно создать документ."""
    from documents.folder_structure import ensure_folder_tree
    from documents.models import Folder

    root = ensure_folder_tree(document_type)
    visible = get_visible_folder_tree_nodes(user, root, include_self=True)
    return visible.filter(lft=F('rght') - 1)


def access_scope_matches_user(scope: AccessScope | None, user) -> bool:
    if scope is None:
        return True
    if scope.is_global or scope.is_unrestricted():
        return True

    role = getattr(user, 'role', None)
    if role and role in (scope.roles or []):
        return True

    if scope.users.filter(pk=user.pk).exists():
        return True

    employee = getattr(user, 'employee_info', None)
    if employee and employee.department_id:
        if scope.departments.filter(pk=employee.department_id).exists():
            return True

    return False


def _allowed_counterparty_type_ids(user) -> list[int]:
    from onec.models import CounterpartyType

    allowed = []
    for counterparty_type in CounterpartyType.objects.filter(is_active=True).select_related('access_scope'):
        scope = counterparty_type.access_scope
        if access_scope_matches_user(scope, user):
            allowed.append(counterparty_type.pk)
    return allowed


def filter_counterparties_queryset(queryset, user):
    if user_has_full_counterparty_access(user):
        return queryset

    allowed_types = _allowed_counterparty_type_ids(user)
    return queryset.filter(
        Q(counterparty_type__isnull=True) | Q(counterparty_type_id__in=allowed_types)
    )


def get_visible_counterparties(user):
    from onec.models import Counterparty

    return filter_counterparties_queryset(Counterparty.objects.all(), user)


def user_can_view_counterparty(user, counterparty) -> bool:
    if user_has_full_counterparty_access(user):
        return True
    if not counterparty.counterparty_type_id:
        return True
    counterparty_type = counterparty.counterparty_type
    return access_scope_matches_user(counterparty_type.access_scope, user)

def filter_suppliers_queryset(queryset, user):
    if user_has_full_access(user):
        return queryset

    from onec.models import Counterparty

    linked_onec_ids = set(
        Counterparty.objects.exclude(id_1c__isnull=True).exclude(id_1c='').values_list('id_1c', flat=True)
    )
    visible_onec_ids = set(
        get_visible_counterparties(user).values_list('id_1c', flat=True)
    )
    hidden_onec_ids = linked_onec_ids - visible_onec_ids

    return queryset.exclude(onec_id__in=hidden_onec_ids)


def user_can_view_supplier(user, supplier) -> bool:
    if user_has_full_access(user):
        return True
    if not supplier.onec_id:
        return True
    from onec.models import Counterparty
    counterparty = Counterparty.objects.filter(id_1c=supplier.onec_id).first()
    if counterparty is None:
        return True
    return user_can_view_counterparty(user, counterparty)
