from project.enums import CustomEnum


class TaskStatusEnum(CustomEnum):
    CREATED = ("created", "Создана")
    ACCEPTED = ("accepted", "Принята")
    REJECTED = ("rejected", "Отклонена")
    REVISION = ("revision", "На доработке")
    COMPLETED = ("completed", "Завершена")

    @classmethod
    def get_full(cls):
        full = {
            cls.CREATED.value[0]: {
                'title': cls.CREATED.value[1],
                'icon': 'flag',
                'color': 'secondary',
            },
            cls.ACCEPTED.value[0]: {
                'title': cls.ACCEPTED.value[1],
                'icon': 'check',
                'color': 'primary',
            },
            cls.REJECTED.value[0]: {
                'title': cls.REJECTED.value[1],
                'icon': 'close',
                'color': 'danger',
            },
            cls.REVISION.value[0]: {
                'title': cls.REVISION.value[1],
                'icon': 'edit',
                'color': 'warning',
            },
            cls.COMPLETED.value[0]: {
                'title': cls.COMPLETED.value[1],
                'icon': 'check',
                'color': 'success',
            },
        }

        return full

    @classmethod
    def get_info(cls, status):
        res = cls.get_full()
        return res.get(status, {})

    @classmethod
    def get_actions(cls, status):
        actions = {
            cls.CREATED.value[0]: [
                {
                    'title': 'Принять',
                    'color': 'primary',
                    'action': 'accept',
                    'next': cls.ACCEPTED.value[0],
                },
                {
                    'title': 'Отклонить',
                    'color': 'danger',
                    'action': 'reject',
                    'next': cls.REJECTED.value[0],
                },
                {
                    'title': 'Отмена',
                    'color': 'outline-dark',
                    'action': 'cancel',
                },
            ],
            cls.ACCEPTED.value[0]: [
                {
                    'title': 'Завершить',
                    'color': 'success',
                    'action': 'complete',
                    'next': cls.COMPLETED.value[0],
                },
                {
                    'title': 'Отмена',
                    'color': 'outline-dark',
                    'action': 'cancel',
                },
            ],
            cls.COMPLETED.value[0]: [
                {
                    'title': 'На доработку',
                    'color': 'warning',
                    'action': 'revision',
                    'next': cls.REVISION.value[0],
                },
                {
                    'title': 'Отмена',
                    'color': 'outline-dark',
                    'action': 'cancel',
                },
            ],
            cls.REVISION.value[0]: [
                {
                    'title': 'Принять',
                    'color': 'primary',
                    'action': 'accept',
                    'next': cls.ACCEPTED.value[0],
                },
                {
                    'title': 'Отмена',
                    'color': 'outline-dark',
                    'action': 'cancel',
                },
            ],
            cls.REJECTED.value[0]: [
                {
                    'title': 'Переоткрыть',
                    'color': 'secondary',
                    'action': 'reopen',
                    'next': cls.CREATED.value[0],
                },
                {
                    'title': 'Отмена',
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
                'title': 'Новая задача',
                'text': 'Создана новая задача',
            },
            cls.ACCEPTED.value[0]: {
                'title': 'Задача принята',
                'text': 'Задача принята к исполнению',
            },
            cls.REJECTED.value[0]: {
                'title': 'Задача отклонена',
                'text': 'Задача была отклонена',
            },
            cls.REVISION.value[0]: {
                'title': 'Задача отправлена на доработку',
                'text': 'Задача требует доработки',
            },
            cls.COMPLETED.value[0]: {
                'title': 'Задача завершена',
                'text': 'Задача успешно завершена',
            },
        }

        return res.get(status, None)


class PriorityEnum(CustomEnum):
    LOW = ("low", "Низкий")
    MEDIUM = ("medium", "Средний")
    HIGH = ("high", "Высокий")
    CRITICAL = ("critical", "Критический")