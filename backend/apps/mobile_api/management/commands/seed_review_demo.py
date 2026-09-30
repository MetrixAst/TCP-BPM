"""Демо-данные для аккаунта, под которым App Review проверяет приложение.

Apple отклонила сборку по 2.3.3 из-за того, что на скриншотах были видны
только пустые экраны и форма входа. Проверяющему нужен аккаунт, где все
разделы заполнены и основной сценарий можно пройти целиком, поэтому
команда приводит данные к предсказуемому состоянию: отметки за сегодня,
обходы в трёх разных статусах, задачи и заявки.

Команда идемпотентна — повторный запуск пересобирает сегодняшний день
заново, не плодя дубликаты.
"""

from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from account.models import UserAccount
from ecopark.models import (
    PlannedRound, RoundPoint, Route, RoutePoint, RoundVisit,
)
from hr.models import AttendanceRecord
from tasks.enums import TaskStatusEnum
from tasks.models import Task, TaskHistory
from tickets.enums import (
    TicketCategoryEnum, TicketPriorityEnum, TicketStatusEnum,
)
from tickets.models import ServiceRequest, ServiceRequestHistory

# Сервер живёт в UTC, а на скриншотах время должно читаться как местное,
# поэтому расписание задаётся в поясе заказчика. Asia/Almaty без перехода
# на летнее время, так что фиксированного смещения достаточно.
LOCAL_TZ = dt_timezone(timedelta(hours=5))

ROUTE_NAME = 'Ежедневный контроль здания'

POINTS = [
    ('Входная группа', 'Главный вход, 1 этаж'),
    ('Техническое помещение', 'Подвал, венткамера'),
    ('Электрощитовая', 'Подвал, помещение 0-12'),
    ('Эвакуационный выход', '2 этаж, запасной выход'),
    ('Выход на кровлю', '5 этаж, технический люк'),
]

# (начало, конец, статус, сколько точек пройдено)
ROUNDS = [
    (time(6, 0), time(10, 0), PlannedRound.STATUS_COMPLETED, 5),
    (time(10, 0), time(14, 0), PlannedRound.STATUS_IN_PROGRESS, 2),
    (time(14, 0), time(18, 0), PlannedRound.STATUS_PENDING, 0),
]

TASKS = [
    ('Заменить лампы в холле второго этажа',
     'Три светильника не работают, нужна замена ламп.',
     TaskStatusEnum.ACCEPTED.value[0], 'high', 1),
    ('Проверить показания счётчиков воды',
     'Снять показания по всем узлам учёта и внести в журнал.',
     TaskStatusEnum.ACCEPTED.value[0], 'medium', 2),
    ('Подготовить акт осмотра кровли',
     'После осеннего обхода оформить акт и приложить фотографии.',
     TaskStatusEnum.CREATED.value[0], 'medium', 4),
    ('Проверить работу аварийного освещения',
     'Плановая проверка по графику пожарной безопасности.',
     TaskStatusEnum.CREATED.value[0], 'low', 6),
]

TICKETS = [
    ('Не охлаждает кондиционер в переговорной',
     'Кондиционер работает, но воздух идёт тёплый. Нужна диагностика.',
     TicketCategoryEnum.HVAC.value[0], TicketPriorityEnum.HIGH.value[0],
     TicketStatusEnum.IN_PROGRESS.value[0], '305'),
    ('Протечка под раковиной в санузле',
     'Вода подтекает из соединения, под раковиной стоит таз.',
     TicketCategoryEnum.PLUMBING.value[0], TicketPriorityEnum.URGENT.value[0],
     TicketStatusEnum.ACCEPTED.value[0], '212'),
    ('Мигает свет в коридоре',
     'Светильник у лифтового холла мигает с утра.',
     TicketCategoryEnum.ELECTRICAL.value[0], TicketPriorityEnum.MEDIUM.value[0],
     TicketStatusEnum.NEW.value[0], '2 этаж, лифтовой холл'),
    ('Не печатает сетевой принтер',
     'Принтер не виден в сети с нескольких рабочих мест.',
     TicketCategoryEnum.IT.value[0], TicketPriorityEnum.MEDIUM.value[0],
     TicketStatusEnum.DONE.value[0], '408'),
]


class Command(BaseCommand):
    help = 'Наполняет демо-данными аккаунт для проверки в App Store'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='appreview')

    @transaction.atomic
    def handle(self, *args, **options):
        user = UserAccount.objects.filter(username=options['username']).first()
        if user is None:
            raise CommandError(f'Пользователь {options["username"]} не найден')

        employee = getattr(user, 'employee_info', None)
        if employee is None:
            raise CommandError('У пользователя нет профиля сотрудника')

        today = timezone.now().astimezone(LOCAL_TZ).date()

        route = self._sync_route(user)
        self._sync_attendance(employee, today)
        self._sync_rounds(user, employee, route, today)
        self._sync_tasks(user)
        self._sync_tickets(user)

        self.stdout.write(self.style.SUCCESS(
            f'Демо-данные готовы для {user.username} на {today}'
        ))

    def _at(self, day, clock):
        return datetime.combine(day, clock, tzinfo=LOCAL_TZ)

    def _sync_route(self, user):
        """Маршрут и его точки с понятными названиями.

        Прежние назывались «Демо: ...» — такие подписи на скриншотах
        выглядят как заготовка, а не как работающий продукт.
        """
        route, _ = Route.objects.get_or_create(
            name=ROUTE_NAME,
            defaults={'assigned_employee': user},
        )
        if route.assigned_employee_id != user.pk:
            route.assigned_employee = user
            route.save(update_fields=['assigned_employee'])

        # Старый демо-маршрут переиспользуем, чтобы не ломать историю визитов.
        for legacy in Route.objects.filter(name__startswith='Демо:').exclude(pk=route.pk):
            for rp in legacy.route_points.all():
                RoutePoint.objects.get_or_create(
                    route=route, point=rp.point, defaults={'order': rp.order},
                )
            PlannedRound.objects.filter(route=legacy).update(route=route)
            legacy.route_points.all().delete()
            legacy.delete()

        existing = list(route.route_points.select_related('point').order_by('order'))
        for index, (name, location) in enumerate(POINTS, start=1):
            if index <= len(existing):
                point = existing[index - 1].point
                point.name = name
                point.location = location
                point.save(update_fields=['name', 'location'])
                RoutePoint.objects.filter(pk=existing[index - 1].pk).update(order=index)
            else:
                point = RoundPoint.objects.create(name=name, location=location)
                RoutePoint.objects.create(route=route, point=point, order=index)

        return route

    def _sync_attendance(self, employee, today):
        """Приход отмечен, уход ещё нет — экран показывает оба состояния."""
        AttendanceRecord.objects.filter(
            employee=employee, timestamp__date=today,
        ).delete()

        AttendanceRecord.objects.create(
            employee=employee,
            event_type='day_start',
            timestamp=self._at(today, time(8, 47)),
            source=AttendanceRecord.SOURCE_QR,
        )

    def _sync_rounds(self, user, employee, route, today):
        """Три обхода за день: завершённый, текущий и предстоящий."""
        points = [
            rp.point for rp in
            route.route_points.select_related('point').order_by('order')
        ]

        PlannedRound.objects.filter(
            assigned_to=user, planned_start__date=today,
        ).delete()
        RoundVisit.objects.filter(
            employee=employee, created_at__date=today,
        ).delete()

        for start, end, status, done in ROUNDS:
            planned_start = self._at(today, start)
            planned_end = self._at(today, end)
            planned = PlannedRound.objects.create(
                route=route,
                assigned_to=user,
                status=status,
                planned_start=planned_start,
                planned_end=planned_end,
                started_at=planned_start if done else None,
                completed_at=(
                    planned_end - timedelta(minutes=48)
                    if status == PlannedRound.STATUS_COMPLETED else None
                ),
            )

            # created_at у визита — auto_now_add, поэтому время выставляем
            # обновлением: иначе все визиты попадут в текущий момент и
            # прогресс завершённого обхода окажется нулевым.
            step = (planned_end - planned_start) / (len(points) + 1)
            for order, point in enumerate(points[:done], start=1):
                visit = RoundVisit.objects.create(point=point, employee=employee)
                RoundVisit.objects.filter(pk=visit.pk).update(
                    created_at=planned_start + step * order,
                )

            self.stdout.write(
                f'  обход {planned.planned_start:%H:%M}–{planned.planned_end:%H:%M} '
                f'[{status}] {done}/{len(points)}'
            )

    def _sync_tasks(self, user):
        author = (
            UserAccount.objects.filter(role='administrator').first()
            or UserAccount.objects.exclude(pk=user.pk).filter(is_active=True).first()
        )
        today = timezone.localdate()

        for title, text, status, priority, days in TASKS:
            task, created = Task.objects.get_or_create(
                title=title,
                executor=user,
                defaults={
                    'text': text,
                    'status': status,
                    'priority': priority,
                    'task_type': 'assignment',
                    'deadline': today + timedelta(days=days),
                    'author': author,
                },
            )
            if created:
                TaskHistory.objects.create(task=task, user=author, status=status)
            else:
                task.deadline = today + timedelta(days=days)
                task.status = status
                task.save(update_fields=['deadline', 'status'])

    def _sync_tickets(self, user):
        for title, description, category, priority, status, room in TICKETS:
            ticket, created = ServiceRequest.objects.get_or_create(
                title=title,
                author=user,
                defaults={
                    'description': description,
                    'category': category,
                    'priority': priority,
                    'status': status,
                    'room': room,
                },
            )
            if created:
                ServiceRequestHistory.objects.create(
                    request=ticket, user=user, status=TicketStatusEnum.NEW.value[0],
                )
                if status != TicketStatusEnum.NEW.value[0]:
                    ServiceRequestHistory.objects.create(
                        request=ticket, user=user, status=status,
                    )
