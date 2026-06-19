from django.utils.translation import gettext_lazy as _
from project.enums import CustomEnum


class TaskStatusEnum(CustomEnum):
    CREATED   = ("created",   _("Создана"))
    ACCEPTED  = ("accepted",  _("Принята"))
    REJECTED  = ("rejected",  _("Отклонена"))
    REVISION  = ("revision",  _("На доработке"))
    COMPLETED = ("completed", _("Завершена"))

    @classmethod
    def get_full(cls):
        return {
            cls.CREATED.value[0]: {
                'title': str(cls.CREATED.value[1]),
                'color': 'neutral',
            },
            cls.ACCEPTED.value[0]: {
                'title': str(cls.ACCEPTED.value[1]),
                'color': 'info',
            },
            cls.REJECTED.value[0]: {
                'title': str(cls.REJECTED.value[1]),
                'color': 'danger',
            },
            cls.REVISION.value[0]: {
                'title': str(cls.REVISION.value[1]),
                'color': 'warning',
            },
            cls.COMPLETED.value[0]: {
                'title': str(cls.COMPLETED.value[1]),
                'color': 'success',
            },
        }

    @classmethod
    def get_info(cls, status):
        return cls.get_full().get(status, {})

    @classmethod
    def get_actions(cls, status):
        actions = {
            cls.CREATED.value[0]: [
                {
                    'title': str(_('Принять')),
                    'color': 'primary',
                    'action': 'accept',
                    'next': cls.ACCEPTED.value[0],
                },
                {
                    'title': str(_('Отклонить')),
                    'color': 'danger',
                    'action': 'reject',
                    'next': cls.REJECTED.value[0],
                },
                {
                    'title': str(_('Отмена')),
                    'color': 'outline-dark',
                    'action': 'cancel',
                },
            ],
            cls.ACCEPTED.value[0]: [
                {
                    'title': str(_('Завершить')),
                    'color': 'success',
                    'action': 'complete',
                    'next': cls.COMPLETED.value[0],
                },
                {
                    'title': str(_('Отмена')),
                    'color': 'outline-dark',
                    'action': 'cancel',
                },
            ],
            cls.COMPLETED.value[0]: [
                {
                    'title': str(_('На доработку')),
                    'color': 'warning',
                    'action': 'revision',
                    'next': cls.REVISION.value[0],
                },
                {
                    'title': str(_('Отмена')),
                    'color': 'outline-dark',
                    'action': 'cancel',
                },
            ],
            cls.REVISION.value[0]: [
                {
                    'title': str(_('Принять')),
                    'color': 'primary',
                    'action': 'accept',
                    'next': cls.ACCEPTED.value[0],
                },
                {
                    'title': str(_('Отмена')),
                    'color': 'outline-dark',
                    'action': 'cancel',
                },
            ],
            cls.REJECTED.value[0]: [
                {
                    'title': str(_('Переоткрыть')),
                    'color': 'secondary',
                    'action': 'reopen',
                    'next': cls.CREATED.value[0],
                },
                {
                    'title': str(_('Отмена')),
                    'color': 'outline-dark',
                    'action': 'cancel',
                },
            ],
        }
        return actions.get(status, None)

    @classmethod
    def get_notification_text(cls, status):
        res = {
            cls.CREATED.value[0]: {
                'title': str(_('Новая задача')),
                'text':  str(_('Создана новая задача')),
            },
            cls.ACCEPTED.value[0]: {
                'title': str(_('Задача принята')),
                'text':  str(_('Задача принята к исполнению')),
            },
            cls.REJECTED.value[0]: {
                'title': str(_('Задача отклонена')),
                'text':  str(_('Задача была отклонена')),
            },
            cls.REVISION.value[0]: {
                'title': str(_('Задача отправлена на доработку')),
                'text':  str(_('Задача требует доработки')),
            },
            cls.COMPLETED.value[0]: {
                'title': str(_('Задача завершена')),
                'text':  str(_('Задача успешно завершена')),
            },
        }
        return res.get(status, None)


class PriorityEnum(CustomEnum):
    LOW      = ("low",      _("Низкий"))
    MEDIUM   = ("medium",   _("Средний"))
    HIGH     = ("high",     _("Высокий"))
    CRITICAL = ("critical", _("Критический"))


class TaskTypeEnum(CustomEnum):
    ASSIGNMENT = ("assignment", _("Поручение"))
    APPROVAL   = ("approval",  _("Согласование"))
    DOCUMENT   = ("document",  _("Документ"))