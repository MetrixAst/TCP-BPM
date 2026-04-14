from project.enums import CustomEnum

class TaskStatusEnum(CustomEnum):
    TO_DO = ("to_do", "На исполение")
    DOING = ("doing", "Выполняется")
    DONE = ("done", "Выполнено")
    ARCHIVE = ("archive", "Архив")

    @classmethod
    def get_full(cls):
        full = {
            cls.TO_DO.value[0]: {
                'title': cls.TO_DO.value[1],
                'icon': 'flag',
                'color': 'secondary',
            },
            cls.DOING.value[0]: {
                'title': cls.DOING.value[1],
                'icon': 'toy',
                'color': 'primary'
            },
            cls.DONE.value[0]: {
                'title': cls.DONE.value[1],
                'icon': 'check',
                'color': 'success'
            },
            cls.ARCHIVE.value[0]: {
                'title': cls.ARCHIVE.value[1],
                'icon': 'bin',
                'color': 'warning'
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
            cls.TO_DO.value[0]: [
                {
                    'title': 'Выполняется',
                    'color': 'primary',
                    'action': 'confirm', 
                    'next': cls.DOING.value[0],
                },
                {
                    'title': 'Отмена',
                    'color': 'outline-dark',
                    'action': 'cancel', 
                },
            ],
            cls.DOING.value[0]: [
                {
                    'title': 'Выполнено',
                    'color': 'tertiary',
                    'action': 'confirm', 
                    'next': cls.DONE.value[0],
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
            cls.TO_DO.value[0]: {
                'title': 'Новая задача',
                'text': 'Добавлена новая задача',
            },
            cls.DOING.value[0]: {
                'title': 'Задача выполняется',
                'text': 'Задача перенесена в статус "Выполняется"',
            },
            cls.DONE.value[0]: {
                'title': 'Задача выполнена',
                'text': 'Задача перенесена в статус "Выполнено"',
            },
            cls.ARCHIVE.value[0]: {
                'title': 'Задача отправлена в архив',
                'text': 'Задача перенесена в статус "Архив"',
            },
        }

        return res.get(status, None)
    