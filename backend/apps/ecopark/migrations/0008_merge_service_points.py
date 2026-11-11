"""
Один QR на помещение: сливаем точки «[Клининг] X» и «[Эксплуатация] X»
(и исходную точку «X», если она есть) в одну. Раньше одно помещение
заводили отдельной точкой и отдельным QR на каждую службу
(команда seed_service_round_points). Теперь у точки чек-листы по отделам
(RoundPointChecklist), и каждый сотрудник получает свой.

Миграция применяется сама при деплое, отдельных команд на сервере не нужно.
Новых точек не создаёт — только сливает существующие.
"""
from django.db import migrations
from django.db.models import Q

PREFIXES = ('[Клининг] ', '[Эксплуатация] ')


def _norm(name):
    for quote in '«»“”':
        name = name.replace(quote, '"')
    return ' '.join(name.split())


def _base_name(name):
    for prefix in PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def merge_service_points(apps, schema_editor):
    RoundPoint = apps.get_model('ecopark', 'RoundPoint')
    RoundPointChecklist = apps.get_model('ecopark', 'RoundPointChecklist')
    RoundVisit = apps.get_model('ecopark', 'RoundVisit')
    Defect = apps.get_model('ecopark', 'Defect')
    Equipment = apps.get_model('ecopark', 'Equipment')
    RoutePoint = apps.get_model('ecopark', 'RoutePoint')

    def ensure_rule(point, checklist_id, department_id, interval):
        if not checklist_id:
            return
        exists = RoundPointChecklist.objects.filter(
            point=point, checklist_id=checklist_id, department_id=department_id, position__isnull=True,
        ).exists()
        if not exists:
            RoundPointChecklist.objects.create(
                point=point, checklist_id=checklist_id, department_id=department_id,
                check_interval_hours=interval, order=RoundPointChecklist.objects.filter(point=point).count(),
            )

    def main_checklist_to_rule(point):
        """Основной чек-лист точки → правило для её ответственного отдела."""
        if not point.checklist_id:
            return
        # Отметки без ответов (чек-лист не проставился из 0007) относим к нему же.
        RoundVisit.objects.filter(point=point, checklist__isnull=True).update(checklist_id=point.checklist_id)
        ensure_rule(point, point.checklist_id, point.responsible_department_id, point.check_interval_hours)

    groups = {}
    for point in RoundPoint.objects.filter(Q(name__startswith=PREFIXES[0]) | Q(name__startswith=PREFIXES[1])):
        groups.setdefault(_norm(_base_name(point.name)), []).append(point)
    if not groups:
        return

    originals = {}
    for point in RoundPoint.objects.exclude(name__startswith='['):
        key = _norm(point.name)
        if key in groups:
            originals.setdefault(key, []).append(point)

    for key, prefixed in groups.items():
        # Порядок выбора общей точки: исходная, эксплуатация, клининг;
        # включённые раньше выключенных.
        prefixed.sort(key=lambda p: (not p.name.startswith(PREFIXES[1]), p.pk))
        candidates = sorted(originals.get(key, []), key=lambda p: p.pk) + prefixed
        candidates.sort(key=lambda p: not p.is_active)
        target, others = candidates[0], candidates[1:]

        main_checklist_to_rule(target)
        for other in others:
            main_checklist_to_rule(other)
            for rule in RoundPointChecklist.objects.filter(point=other):
                if not RoundPointChecklist.objects.filter(
                    point=target, checklist_id=rule.checklist_id,
                    department_id=rule.department_id, position_id=rule.position_id,
                ).exists():
                    rule.point = target
                    rule.order = RoundPointChecklist.objects.filter(point=target).count()
                    rule.save(update_fields=['point', 'order'])
            RoundPointChecklist.objects.filter(point=other).delete()

            RoundVisit.objects.filter(point=other).update(point=target)
            Defect.objects.filter(point=other).update(point=target)
            Equipment.objects.filter(point=other).update(point=target)
            for route_point in RoutePoint.objects.filter(point=other):
                if RoutePoint.objects.filter(route_id=route_point.route_id, point=target).exists():
                    route_point.delete()
                else:
                    route_point.point = target
                    route_point.save(update_fields=['point'])

            other.is_active = False
            other.save(update_fields=['is_active'])

        target.name = _base_name(target.name)
        target.checklist = None
        target.responsible_department = None
        target.save(update_fields=['name', 'checklist', 'responsible_department'])


class Migration(migrations.Migration):

    dependencies = [
        ('ecopark', '0007_room_qr_checklists'),
    ]

    operations = [
        migrations.RunPython(merge_service_points, migrations.RunPython.noop),
    ]
