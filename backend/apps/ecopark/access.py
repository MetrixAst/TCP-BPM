from django.db.models import Q
from django.utils import timezone


def user_has_round_assignment(user):
    """Whether the user has ever received or can receive an active round."""
    if not getattr(user, 'is_authenticated', False):
        return False

    from ecopark.models import PlannedRound, Route

    if PlannedRound.objects.filter(assigned_to=user).exists():
        return True

    assignment = Q(assigned_employee=user)
    employee = getattr(user, 'employee_info', None)
    if employee and employee.department_id:
        assignment |= Q(assigned_department_id=employee.department_id)

    now = timezone.now()
    assignment |= Q(
        substitute_employee=user,
        substitute_from__lte=now,
        substitute_to__gte=now,
    )

    return Route.objects.filter(is_active=True).filter(assignment).exists()
