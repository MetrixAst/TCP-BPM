from account.role_permissions import RoleEnums


def get_visible_folders(user, queryset=None):
    from documents.models import Folder
    from onec.models import AccessScope

    if queryset is None:
        queryset = Folder.objects.all()

    role = user.role.value if hasattr(user.role, 'value') else user.role

    if role in (
        RoleEnums.ADMINISTRATOR.value,
        RoleEnums.OWNER.value,
        RoleEnums.CFO.value,
        RoleEnums.CHIEF_ACCOUNTANT.value,
    ):
        return queryset

    scopes = AccessScope.objects.filter(users=user)
    if not scopes.exists():
        return queryset

    from django.db.models import Q
    folder_ids = scopes.values_list('folders', flat=True).distinct()
    return queryset.filter(pk__in=folder_ids)