"""
Слияние точек обхода в одну: раньше одно помещение заводили несколькими
точками — по точке и QR на каждую службу. Теперь у помещения один QR, а
чек-листы служб задаются правилами (RoundPointChecklist).
"""
from django.db import transaction


def ensure_rule(point, checklist, department=None, position=None, interval_hours=None):
    """Правило «отдел/должность → чек-лист» на точке, без дублей."""
    from .models import RoundPointChecklist

    rule = RoundPointChecklist.objects.filter(
        point=point, department=department, position=position, checklist=checklist,
    ).first()
    if rule is None:
        rule = RoundPointChecklist.objects.create(
            point=point, checklist=checklist, department=department, position=position,
            check_interval_hours=interval_hours, order=point.checklist_rules.count(),
        )
    elif interval_hours and rule.check_interval_hours != interval_hours:
        rule.check_interval_hours = interval_hours
        rule.save(update_fields=['check_interval_hours'])
    return rule


@transaction.atomic
def merge_points(target, sources):
    """
    Переносит на target всё, что было на sources: отметки, неисправности,
    оборудование, места в маршрутах и чек-листы (как правила для их отделов).
    Исходные точки деактивируются — их старые QR перестают работать, а вся
    история теперь на target.
    """
    from .models import Defect, Equipment, RoutePoint, RoundVisit

    for source in sources:
        if source.pk == target.pk:
            continue

        if source.checklist_id:
            ensure_rule(
                target, source.checklist,
                department=source.responsible_department,
                interval_hours=source.check_interval_hours,
            )
        for rule in source.checklist_rules.all():
            ensure_rule(target, rule.checklist, rule.department, rule.position, rule.check_interval_hours)
        source.checklist_rules.all().delete()

        RoundVisit.objects.filter(point=source).update(point=target)
        Defect.objects.filter(point=source).update(point=target)
        Equipment.objects.filter(point=source).update(point=target)
        for route_point in RoutePoint.objects.filter(point=source):
            if RoutePoint.objects.filter(route=route_point.route, point=target).exists():
                route_point.delete()
            else:
                route_point.point = target
                route_point.save(update_fields=['point'])

        source.is_active = False
        source.save(update_fields=['is_active'])
