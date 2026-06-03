from onec.models import Counterparty
from account.role_permissions import RoleEnums


def get_visible_counterparties(user, queryset=None):
    if queryset is None:
        queryset = Counterparty.objects.all()

    if user.role in (
        RoleEnums.ADMINISTRATOR.value,
        RoleEnums.OWNER.value,
        RoleEnums.CFO.value,
        RoleEnums.CHIEF_ACCOUNTANT.value,
    ):
        return queryset

    from onec.models import AccessScope
    scopes = AccessScope.objects.filter(users=user)

    if scopes.exists():
        counterparty_ids = scopes.values_list(
            'counterparties__id', flat=True
        ).distinct()
        return queryset.filter(id__in=counterparty_ids)
    return queryset