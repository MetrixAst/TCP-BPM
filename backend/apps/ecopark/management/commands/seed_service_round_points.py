"""
Служебные помещения: одна точка обхода и один QR на помещение. Клининг и
эксплуатация сканируют один код, а приложение выдаёт каждому чек-лист его
отдела (правила RoundPointChecklist).

Раньше команда заводила на помещение две точки — «[Клининг] …» и
«[Эксплуатация] …» со своими QR. При запуске такие пары сливаются в одну
точку: отметки, неисправности, оборудование и маршруты переносятся, старые
точки деактивируются.

Идемпотентно: повторный запуск ничего не дублирует.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from account.models import Department
from ecopark.models import ChecklistItem, ChecklistTemplate, EcoObject, RoundPoint
from ecopark.point_merge import ensure_rule, merge_points


CLEANING_CHECKLIST = {
    'name': 'Клининг — служебное помещение',
    'items': [
        'Пол чистый, без мусора и луж',
        'Корзины / мешки для мусора опустошены или заменены',
        'Санузел / раковина (если есть) в порядке',
        'Расходники пополнены (мыло, бумага, мешки)',
        'Запахи и вентиляция в норме',
        'Замечания зафиксированы (при наличии)',
    ],
}

OPS_CHECKLIST = {
    'name': 'Эксплуатация — служебное помещение',
    'items': [
        'Дверь / замок / доступ исправны',
        'Освещение работает',
        'Нет протечек, посторонних запахов, задымления',
        'Оборудование / щиты / вент. узлы без аварийных признаков',
        'Проходы свободны, эвакуационные пути не перекрыты',
        'Замечания / дефекты зафиксированы',
    ],
}

# Помещение → одна точка, чек-листы клининга и эксплуатации со своими интервалами
SERVICE_ROOMS = [
    {
        'room_key': 'entrance',
        'base_name': 'Входная группа',
        'location': 'Главный вход, 1 этаж',
        'eco_object': 'Общие зоны ТРЦ',
        'interval_cleaning': 8,
        'interval_ops': 24,
    },
    {
        'room_key': 'tech',
        'base_name': 'Техническое помещение',
        'location': 'Подвал, венткамера',
        'eco_object': 'Вентиляция и кондиционирование',
        'interval_cleaning': 24,
        'interval_ops': 12,
    },
    {
        'room_key': 'roof',
        'base_name': 'Выход на кровлю',
        'location': '5 этаж, технический люк',
        'eco_object': 'Общие зоны ТРЦ',
        'interval_cleaning': 24,
        'interval_ops': 24,
    },
    {
        'room_key': 'evac',
        'base_name': 'Эвакуационный выход',
        'location': '2 этаж, запасной выход',
        'eco_object': 'Общие зоны ТРЦ',
        'interval_cleaning': 12,
        'interval_ops': 24,
    },
    {
        'room_key': 'electrical',
        'base_name': 'Электрощитовая',
        'location': 'Подвал, помещение 0-12',
        'eco_object': 'Электроснабжение',
        'interval_cleaning': 168,  # раз в неделю
        'interval_ops': 24,
    },
    {
        'room_key': 'cleaning_room',
        'base_name': 'Комната клининга',
        'location': 'Служебный блок',
        'eco_object': 'Общие зоны ТРЦ',
        'interval_cleaning': 8,
        'interval_ops': 48,
    },
    {
        'room_key': 'aho',
        'base_name': 'Помещение АХО',
        'location': 'Служебный блок',
        'eco_object': 'Общие зоны ТРЦ',
        'interval_cleaning': 24,
        'interval_ops': 24,
    },
]

# Боевые комнаты на сервере: исходная точка (source_names) становится общей —
# её QR, если уже напечатан, продолжает работать для обеих служб.
PRODUCTION_ROOMS = [
    {
        'room_key': 'prod_cleaning',
        'base_name': 'Комната Клининга',
        'location': '',
        'eco_object': 'Общие зоны ТРЦ',
        'interval_cleaning': 8,
        'interval_ops': 48,
        'source_names': ['Комната Клининга'],
    },
    {
        'room_key': 'prod_aho',
        'base_name': 'Комната отдела АХО',
        'location': '',
        'eco_object': 'Общие зоны ТРЦ',
        'interval_cleaning': 24,
        'interval_ops': 24,
        'source_names': ['Комната отдела АХО'],
    },
    {
        'room_key': 'prod_ops',
        'base_name': 'Комната Эксплуатации',
        'location': '',
        'eco_object': 'Общие зоны ТРЦ',
        'interval_cleaning': 24,
        'interval_ops': 12,
        'source_names': ['Комната Эксплуатации'],
    },
    {
        'room_key': 'prod_sliv1',
        'base_name': 'Комната «Слив 1»',
        'location': '1 этаж',
        'eco_object': 'Общие зоны ТРЦ',
        'interval_cleaning': 8,
        'interval_ops': 24,
        'source_names': ['Комната "Слив 1"'],
    },
    {
        'room_key': 'prod_sliv2',
        'base_name': 'Комната «Слив 2»',
        'location': '',
        'eco_object': 'Общие зоны ТРЦ',
        'interval_cleaning': 8,
        'interval_ops': 24,
        'source_names': ['Комната "Слив 2"'],
    },
]

SERVICE_PREFIXES = ('Эксплуатация', 'Клининг')


def _ensure_checklist(spec: dict) -> ChecklistTemplate:
    template, _ = ChecklistTemplate.objects.get_or_create(
        name=spec['name'],
        defaults={'is_active': True},
    )
    if not template.is_active:
        template.is_active = True
        template.save(update_fields=['is_active'])

    existing = {item.order: item for item in template.items.all()}
    for order, text in enumerate(spec['items'], start=1):
        item = existing.get(order)
        if item is None:
            ChecklistItem.objects.create(
                template=template,
                order=order,
                text=text,
                requires_photo_on_fail=True,
            )
        elif item.text != text:
            item.text = text
            item.save(update_fields=['text'])
    return template


def _dept_by_name(*names: str) -> Department | None:
    for name in names:
        dept = Department.objects.filter(name__iexact=name).first()
        if dept:
            return dept
        dept = Department.objects.filter(name__icontains=name).first()
        if dept:
            return dept
    return None


def _eco_by_name(name: str) -> EcoObject | None:
    if not name:
        return None
    obj, _ = EcoObject.objects.get_or_create(name=name, defaults={'is_active': True})
    return obj


def _point_name(prefix: str, base_name: str) -> str:
    return f'[{prefix}] {base_name}'


def _find_room_points(room: dict) -> list[RoundPoint]:
    """Все точки этого помещения: исходная боевая, без префикса и старые
    «[Эксплуатация] …» / «[Клининг] …». Первая станет общей — её QR сохраняется."""
    names = list(room.get('source_names') or []) + [room['base_name']] + [
        _point_name(prefix, room['base_name']) for prefix in SERVICE_PREFIXES
    ]
    points = []
    for name in names:
        for point in RoundPoint.objects.filter(name=name).order_by('pk'):
            if point not in points:
                points.append(point)
    # Общей делаем включённую точку, чтобы помещение не выпало из обхода;
    # среди включённых — по порядку names (исходная боевая точка первой).
    points.sort(key=lambda point: not point.is_active)
    return points


class Command(BaseCommand):
    help = (
        'Служебные помещения: одна точка и один QR на помещение, чек-листы '
        'клининга и эксплуатации по отделу. Сливает старые пары точек [Клининг]/[Эксплуатация].'
    )

    def add_arguments(self, parser):
        # Оставлен, чтобы не ломать старые инструкции запуска: старые точки
        # теперь сливаются в общие всегда.
        parser.add_argument('--deactivate-legacy', action='store_true', help='Больше не нужен')

    @transaction.atomic
    def handle(self, *args, **options):
        cleaning_dept = _dept_by_name('Клининг')
        ops_dept = _dept_by_name('Эксплуатация')
        if cleaning_dept is None:
            self.stdout.write(self.style.WARNING('Отдел «Клининг» не найден — чек-лист клининга не назначен'))
        if ops_dept is None:
            self.stdout.write(self.style.WARNING('Отдел «Эксплуатация» не найден — чек-лист эксплуатации не назначен'))

        cleaning_cl = _ensure_checklist(CLEANING_CHECKLIST)
        ops_cl = _ensure_checklist(OPS_CHECKLIST)
        self.stdout.write(f'Чек-листы: «{cleaning_cl.name}», «{ops_cl.name}»')

        created = merged = 0
        for room in SERVICE_ROOMS + PRODUCTION_ROOMS:
            points = _find_room_points(room)
            if points:
                point, others = points[0], points[1:]
            else:
                point, others = RoundPoint.objects.create(name=room['base_name']), []
                created += 1

            # Чек-листы служб — правилами по отделу, а не основным чек-листом точки.
            if room.get('source_names') is None or point.name not in room['source_names']:
                point.name = room['base_name']
            point.location = room['location'] or point.location
            point.eco_object = _eco_by_name(room['eco_object']) or point.eco_object
            point.checklist = None
            point.responsible_department = None
            point.check_interval_hours = min(room['interval_cleaning'], room['interval_ops'])
            # is_active не трогаем: помещение, выключенное админом на сайте
            # (например, демо, которого нет в этом ТРЦ), остаётся выключенным.
            point.save()

            if others:
                merge_points(point, others)
                merged += len(others)
            # Правила, перенесённые слиянием со старых точек, заменяем эталонными.
            point.checklist_rules.filter(checklist__in=[cleaning_cl, ops_cl]).exclude(
                department__in=[d for d in (cleaning_dept, ops_dept) if d],
            ).delete()
            for dept, checklist, interval in (
                (cleaning_dept, cleaning_cl, room['interval_cleaning']),
                (ops_dept, ops_cl, room['interval_ops']),
            ):
                if dept is not None:
                    ensure_rule(point, checklist, department=dept, interval_hours=interval)

            merged_note = f' (слиты: {", ".join(p.name for p in others)})' if others else ''
            self.stdout.write(f'  {point.name}  QR={point.uuid}{merged_note}')

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово: создано точек {created}, слито старых точек {merged}. '
            f'Старые QR [Клининг]/[Эксплуатация] больше не действуют — распечатайте QR общих точек: '
            f'/ecopark/rounds/points/<id>/label/'
        ))
