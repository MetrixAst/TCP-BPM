from django.utils.translation import gettext_lazy as _
from project.enums import CustomEnum


class TicketCategoryEnum(CustomEnum):
    ELECTRICAL = ("electrical", _("Электрика"))
    PLUMBING   = ("plumbing",   _("Сантехника"))
    HVAC       = ("hvac",       _("Вентиляция и кондиционирование"))
    CLEANING   = ("cleaning",   _("Клининг"))
    FURNITURE  = ("furniture",  _("Мебель и фурнитура"))
    IT         = ("it",         _("ИТ и связь"))
    SECURITY   = ("security",   _("Безопасность"))
    OTHER      = ("other",      _("Прочее"))


class TicketPriorityEnum(CustomEnum):
    LOW    = ("low",    _("Низкий"))
    MEDIUM = ("medium", _("Средний"))
    HIGH   = ("high",   _("Высокий"))
    URGENT = ("urgent", _("Срочный"))

    @classmethod
    def get_info(cls, priority):
        meta = {
            cls.LOW.value[0]:    {'title': str(cls.LOW.value[1]),    'color': 'neutral'},
            cls.MEDIUM.value[0]: {'title': str(cls.MEDIUM.value[1]), 'color': 'info'},
            cls.HIGH.value[0]:   {'title': str(cls.HIGH.value[1]),   'color': 'warning'},
            cls.URGENT.value[0]: {'title': str(cls.URGENT.value[1]), 'color': 'danger'},
        }
        return meta.get(priority, {'title': priority, 'color': 'neutral'})


class TicketStatusEnum(CustomEnum):
    NEW         = ("new",         _("Новая"))
    ACCEPTED    = ("accepted",    _("Принята"))
    IN_PROGRESS = ("in_progress", _("В работе"))
    DONE        = ("done",        _("Выполнена"))
    REJECTED    = ("rejected",    _("Отклонена"))
    CANCELLED   = ("cancelled",   _("Отменена"))

    @classmethod
    def get_full(cls):
        return {
            cls.NEW.value[0]:         {'title': str(cls.NEW.value[1]),         'color': 'warning', 'icon': 'bi-inbox'},
            cls.ACCEPTED.value[0]:    {'title': str(cls.ACCEPTED.value[1]),    'color': 'info',    'icon': 'bi-check2-circle'},
            cls.IN_PROGRESS.value[0]: {'title': str(cls.IN_PROGRESS.value[1]), 'color': 'primary', 'icon': 'bi-tools'},
            cls.DONE.value[0]:        {'title': str(cls.DONE.value[1]),        'color': 'success', 'icon': 'bi-check-circle-fill'},
            cls.REJECTED.value[0]:    {'title': str(cls.REJECTED.value[1]),    'color': 'danger',  'icon': 'bi-x-circle'},
            cls.CANCELLED.value[0]:   {'title': str(cls.CANCELLED.value[1]),   'color': 'neutral', 'icon': 'bi-slash-circle'},
        }

    @classmethod
    def get_info(cls, status):
        return cls.get_full().get(status, {'title': status, 'color': 'neutral', 'icon': 'bi-circle'})

    @classmethod
    def board_statuses(cls):
        return [cls.NEW, cls.ACCEPTED, cls.IN_PROGRESS, cls.DONE, cls.REJECTED]


TICKET_TRANSITIONS = {
    TicketStatusEnum.NEW.value[0]: {
        'accept': {'next': TicketStatusEnum.ACCEPTED.value[0],  'roles': ['manager'],
                   'title': str(_('Принять в работу')),  'variant': 'success'},
        'reject': {'next': TicketStatusEnum.REJECTED.value[0],  'roles': ['manager'],
                   'title': str(_('Отклонить')),         'variant': 'danger'},
        'cancel': {'next': TicketStatusEnum.CANCELLED.value[0], 'roles': ['author'],
                   'title': str(_('Отозвать заявку')),   'variant': 'danger'},
    },
    TicketStatusEnum.ACCEPTED.value[0]: {
        'start':  {'next': TicketStatusEnum.IN_PROGRESS.value[0], 'roles': ['manager'],
                   'title': str(_('Начать выполнение')), 'variant': 'primary'},
        'reject': {'next': TicketStatusEnum.REJECTED.value[0],    'roles': ['manager'],
                   'title': str(_('Отклонить')),         'variant': 'danger'},
    },
    TicketStatusEnum.IN_PROGRESS.value[0]: {
        'complete': {'next': TicketStatusEnum.DONE.value[0], 'roles': ['manager'],
                     'title': str(_('Завершить')),       'variant': 'success'},
    },
    TicketStatusEnum.DONE.value[0]: {
        'reopen': {'next': TicketStatusEnum.IN_PROGRESS.value[0], 'roles': ['manager'],
                   'title': str(_('Вернуть в работу')), 'variant': 'warning'},
    },
    TicketStatusEnum.REJECTED.value[0]: {
        'reopen': {'next': TicketStatusEnum.NEW.value[0], 'roles': ['manager'],
                   'title': str(_('Вернуть в новые')),  'variant': 'warning'},
    },
}