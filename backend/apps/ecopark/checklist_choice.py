"""
Какой чек-лист проходит сотрудник на точке обхода.

На помещении один QR, а чек-листов может быть несколько — свой у каждой
службы и должности (RoundPointChecklist). Общие правила для веба
(ecopark:rounds_scan) и мобильного API.
"""
from django.utils import timezone

NOT_CHOSEN = object()


def visit_checklist_options(point, employee, user):
    """
    Чек-листы, доступные сотруднику на точке. Пустой список — отметить точку
    он не может. Назначенному на сегодня маршрут с этой точкой доступны все
    её чек-листы, даже если правила под его должность не подошли: маршрут
    ему выдал диспетчер.
    """
    from .models import PlannedRound

    options = point.checklists_for(employee)
    if options:
        return options
    has_planned_round = PlannedRound.objects.filter(
        assigned_to=user,
        route__route_points__point=point,
        planned_start__date=timezone.localdate(),
    ).exists()
    return point.all_checklists() if has_planned_round else []


def pick_checklist(options, chosen=None, default_first=False):
    """
    Выбранный чек-лист из options. NOT_CHOSEN — сотруднику нужно выбрать
    самому. default_first — для старых версий приложения, которые не умеют
    выбирать: им отдаём первый чек-лист.
    """
    if chosen not in (None, ''):
        for checklist in options:
            if checklist is not None and str(checklist.pk) == str(chosen):
                return checklist
    if len(options) == 1 or (default_first and options):
        return options[0]
    return NOT_CHOSEN


def checklist_options_json(options):
    return [{'id': c.pk, 'name': c.name} for c in options if c is not None]
