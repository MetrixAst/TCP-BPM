from project.enums import CustomEnum


class TicketCategoryEnum(CustomEnum):
    """Категория сервисной заявки от арендатора."""

    ELECTRICAL = ("electrical", "Электрика")
    PLUMBING = ("plumbing", "Сантехника")
    HVAC = ("hvac", "Вентиляция и кондиционирование")
    CLEANING = ("cleaning", "Клининг")
    FURNITURE = ("furniture", "Мебель и фурнитура")
    IT = ("it", "ИТ и связь")
    SECURITY = ("security", "Безопасность")
    OTHER = ("other", "Прочее")


class TicketPriorityEnum(CustomEnum):
    LOW = ("low", "Низкий")
    MEDIUM = ("medium", "Средний")
    HIGH = ("high", "Высокий")
    URGENT = ("urgent", "Срочный")

    @classmethod
    def get_info(cls, priority):
        meta = {
            cls.LOW.value[0]: {'title': cls.LOW.value[1], 'color': 'neutral'},
            cls.MEDIUM.value[0]: {'title': cls.MEDIUM.value[1], 'color': 'info'},
            cls.HIGH.value[0]: {'title': cls.HIGH.value[1], 'color': 'warning'},
            cls.URGENT.value[0]: {'title': cls.URGENT.value[1], 'color': 'danger'},
        }
        return meta.get(priority, {'title': priority, 'color': 'neutral'})


class TicketStatusEnum(CustomEnum):
    NEW = ("new", "Новая")
    ACCEPTED = ("accepted", "Принята")
    IN_PROGRESS = ("in_progress", "В работе")
    DONE = ("done", "Выполнена")
    REJECTED = ("rejected", "Отклонена")
    CANCELLED = ("cancelled", "Отменена")

    @classmethod
    def get_full(cls):
        return {
            cls.NEW.value[0]: {'title': cls.NEW.value[1], 'color': 'warning', 'icon': 'bi-inbox'},
            cls.ACCEPTED.value[0]: {'title': cls.ACCEPTED.value[1], 'color': 'info', 'icon': 'bi-check2-circle'},
            cls.IN_PROGRESS.value[0]: {'title': cls.IN_PROGRESS.value[1], 'color': 'primary', 'icon': 'bi-tools'},
            cls.DONE.value[0]: {'title': cls.DONE.value[1], 'color': 'success', 'icon': 'bi-check-circle-fill'},
            cls.REJECTED.value[0]: {'title': cls.REJECTED.value[1], 'color': 'danger', 'icon': 'bi-x-circle'},
            cls.CANCELLED.value[0]: {'title': cls.CANCELLED.value[1], 'color': 'neutral', 'icon': 'bi-slash-circle'},
        }

    @classmethod
    def get_info(cls, status):
        return cls.get_full().get(status, {'title': status, 'color': 'neutral', 'icon': 'bi-circle'})

    @classmethod
    def board_statuses(cls):
        """Колонки канбана для персонала (без терминальных «отменена»)."""
        return [cls.NEW, cls.ACCEPTED, cls.IN_PROGRESS, cls.DONE, cls.REJECTED]


# Переходы статусов.
# manager — сотрудник, обрабатывающий заявку; author — арендатор/создатель.
TICKET_TRANSITIONS = {
    TicketStatusEnum.NEW.value[0]: {
        'accept': {'next': TicketStatusEnum.ACCEPTED.value[0], 'roles': ['manager'],
                   'title': 'Принять в работу', 'variant': 'success'},
        'reject': {'next': TicketStatusEnum.REJECTED.value[0], 'roles': ['manager'],
                   'title': 'Отклонить', 'variant': 'danger'},
        'cancel': {'next': TicketStatusEnum.CANCELLED.value[0], 'roles': ['author'],
                   'title': 'Отозвать заявку', 'variant': 'danger'},
    },
    TicketStatusEnum.ACCEPTED.value[0]: {
        'start': {'next': TicketStatusEnum.IN_PROGRESS.value[0], 'roles': ['manager'],
                  'title': 'Начать выполнение', 'variant': 'primary'},
        'reject': {'next': TicketStatusEnum.REJECTED.value[0], 'roles': ['manager'],
                   'title': 'Отклонить', 'variant': 'danger'},
    },
    TicketStatusEnum.IN_PROGRESS.value[0]: {
        'complete': {'next': TicketStatusEnum.DONE.value[0], 'roles': ['manager'],
                     'title': 'Завершить', 'variant': 'success'},
    },
    TicketStatusEnum.DONE.value[0]: {
        'reopen': {'next': TicketStatusEnum.IN_PROGRESS.value[0], 'roles': ['manager'],
                   'title': 'Вернуть в работу', 'variant': 'warning'},
    },
    TicketStatusEnum.REJECTED.value[0]: {
        'reopen': {'next': TicketStatusEnum.NEW.value[0], 'roles': ['manager'],
                   'title': 'Вернуть в новые', 'variant': 'warning'},
    },
}
