"""
Разносит служебные помещения на отдельные точки обхода для клининга и эксплуатации:
свой чек-лист, свой отдел, свой QR (uuid точки).

Идемпотентно: повторный запуск обновляет чек-листы/привязки, не дублирует точки.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from account.models import Department
from ecopark.models import ChecklistItem, ChecklistTemplate, EcoObject, RoundPoint


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

# Помещения → две точки: клининг + эксплуатация
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

# Старые демо-точки без префикса отдела → переносим в эксплуатацию
LEGACY_NAME_TO_ROOM = {
    'Входная группа': 'entrance',
    'Техническое помещение': 'tech',
    'Выход на кровлю': 'roof',
    'Эвакуационный выход': 'evac',
    'Электрощитовая': 'electrical',
}


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


class Command(BaseCommand):
    help = (
        'Создаёт отдельные точки обхода для клининга и эксплуатации '
        'со своими чек-листами и QR'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--deactivate-legacy',
            action='store_true',
            help='Деактивировать старые точки без префикса [Клининг]/[Эксплуатация]',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        cleaning_dept = _dept_by_name('Клининг')
        ops_dept = _dept_by_name('Эксплуатация')
        if cleaning_dept is None:
            self.stdout.write(self.style.WARNING('Отдел «Клининг» не найден — точки клининга без отдела'))
        if ops_dept is None:
            self.stdout.write(self.style.WARNING('Отдел «Эксплуатация» не найден — точки эксплуатации без отдела'))

        cleaning_cl = _ensure_checklist(CLEANING_CHECKLIST)
        ops_cl = _ensure_checklist(OPS_CHECKLIST)
        self.stdout.write(f'Чек-листы: «{cleaning_cl.name}», «{ops_cl.name}»')

        created = updated = 0

        # Переименовать legacy-точки в эксплуатационные, если ещё без префикса
        for legacy_name, room_key in LEGACY_NAME_TO_ROOM.items():
            room = next(r for r in SERVICE_ROOMS if r['room_key'] == room_key)
            target = _point_name('Эксплуатация', room['base_name'])
            legacy = RoundPoint.objects.filter(name=legacy_name).first()
            if legacy and not RoundPoint.objects.filter(name=target).exclude(pk=legacy.pk).exists():
                legacy.name = target
                legacy.save(update_fields=['name'])
                self.stdout.write(f'  ~ legacy «{legacy_name}» → «{target}»')

        for room in SERVICE_ROOMS:
            eco = _eco_by_name(room['eco_object'])
            for prefix, dept, checklist, interval in (
                ('Клининг', cleaning_dept, cleaning_cl, room['interval_cleaning']),
                ('Эксплуатация', ops_dept, ops_cl, room['interval_ops']),
            ):
                name = _point_name(prefix, room['base_name'])
                point, was_created = RoundPoint.objects.get_or_create(
                    name=name,
                    defaults={
                        'location': room['location'],
                        'eco_object': eco,
                        'checklist': checklist,
                        'responsible_department': dept,
                        'check_interval_hours': interval,
                        'is_active': True,
                    },
                )
                fields = []
                if point.location != room['location']:
                    point.location = room['location']
                    fields.append('location')
                if point.eco_object_id != (eco.pk if eco else None):
                    point.eco_object = eco
                    fields.append('eco_object')
                if point.checklist_id != checklist.pk:
                    point.checklist = checklist
                    fields.append('checklist')
                if dept and point.responsible_department_id != dept.pk:
                    point.responsible_department = dept
                    fields.append('responsible_department')
                if point.check_interval_hours != interval:
                    point.check_interval_hours = interval
                    fields.append('check_interval_hours')
                if not point.is_active:
                    point.is_active = True
                    fields.append('is_active')
                if fields:
                    point.save(update_fields=fields)
                    updated += 1
                if was_created:
                    created += 1
                    self.stdout.write(f'  + {name}  QR={point.uuid}')
                else:
                    self.stdout.write(f'  = {name}  QR={point.uuid}')

        if options.get('deactivate_legacy'):
            legacy_qs = RoundPoint.objects.exclude(
                name__startswith='[Клининг]',
            ).exclude(
                name__startswith='[Эксплуатация]',
            ).filter(is_active=True)
            n = legacy_qs.update(is_active=False)
            self.stdout.write(f'Деактивировано legacy-точек: {n}')

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово: создано {created}, обновлено {updated}. '
            f'QR-этикетка: /ecopark/rounds/points/<id>/label/'
        ))
