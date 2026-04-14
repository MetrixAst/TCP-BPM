from project.enums import CustomEnum


class RequstionTypesEnum(CustomEnum):

    IMPORT = ("import", "Ввоз")
    EXPORT = ("export", "Вывоз")
    TEMP_PASS = ("temp_pass", "Временный пропуск")
    PERM_PASS = ("perm_pass", "Постоянный пропуск")
    WORKS = ("works", "Проведение работ")


class RequstionStatusEnum(CustomEnum):
    DRAFT = ("draft", "Создан")
    COORDINATION = ("coordination", "Согласование")
    SIGNING = ("signing", "Подписание")
    ACTIVE = ("active", "Действующий")
    ARCHIVE = ("archive", "Архив")
    
    @classmethod
    def get_full(cls, document_type):
        # if document_type == DocumentTypeEnum.PURCHASES.value[0]:
        #     full = {
        #         cls.OFFER.value[0]: {
        #             'title': cls.OFFER.value[1],
        #             'icon': 'trend-up',
        #             'color': 'secondary',
        #         },
        #         cls.MODERATING.value[0]: {
        #             'title': cls.MODERATING.value[1],
        #             'icon': 'activity',
        #             'color': 'danger'
        #         },
        #         cls.COMPLETED.value[0]: {
        #             'title': cls.COMPLETED.value[1],
        #             'icon': 'edit',
        #             'color': 'primary'
        #         },
        #         cls.REFUSED.value[0]: {
        #             'title': cls.REFUSED.value[1],
        #             'icon': 'bin',
        #             'color': 'warning'
        #         },
        #     }
        # else:
        full = {
            cls.DRAFT.value[0]: {
                'title': cls.DRAFT.value[1],
                'icon': 'trend-up',
                'color': 'secondary',
            },
            cls.COORDINATION.value[0]: {
                'title': cls.COORDINATION.value[1],
                'icon': 'activity',
                'color': 'danger'
            },
            cls.SIGNING.value[0]: {
                'title': cls.SIGNING.value[1],
                'icon': 'edit',
                'color': 'primary'
            },
            cls.ACTIVE.value[0]: {
                'title': cls.ACTIVE.value[1],
                'icon': 'form',
                'color': 'quaternary'
            },
            cls.ARCHIVE.value[0]: {
                'title': cls.ARCHIVE.value[1],
                'icon': 'bin',
                'color': 'warning'
            },
        }

        return full

    @classmethod
    def get_info(cls, status, document_type):
        res = cls.get_full(document_type)

        return res.get(status, {})
    
    @classmethod
    def get_actions(cls, status, requistion_type, requistion_user, user):

        # if document_type == DocumentTypeEnum.PURCHASES.value[0]:
        #     actions = {
        #         cls.OFFER.value[0]: [
        #             {
        #                 'title': 'Отправить на согласование',
        #                 'color': 'primary',
        #                 'action': 'confirm', 
        #                 'next': cls.MODERATING.value[0],
        #             },
        #             {
        #                 'title': 'Удалить',
        #                 'color': 'outline-dark',
        #                 'action': 'cancel',
        #                 'permission': 'coordinators',
        #             },
        #         ],
        #         cls.MODERATING.value[0]: [
        #             {
        #                 'title': 'Согласован',
        #                 'color': 'tertiary',
        #                 'action': 'confirm',
        #                 'next': cls.COMPLETED.value[0],
        #                 'permission': 'coordinators',
        #             },
        #         ],
        #     }
        # else:

        if requistion_user == user:
            return [
                {
                    'title': 'Удалить',
                    'color': 'outline-dark',
                    'action': 'cancel', 
                    'permission': 'author',
                },
            ]

        actions = {
            cls.DRAFT.value[0]: [
                {
                    'title': 'Отправить на согласование',
                    'color': 'primary',
                    'action': 'confirm', 
                    'next': cls.COORDINATION.value[0],
                    'permission': 'author',
                },
                {
                    'title': 'Удалить',
                    'color': 'outline-dark',
                    'action': 'cancel', 
                    'permission': 'author',
                },
            ],
            cls.COORDINATION.value[0]: [
                {
                    'title': 'На подписание',
                    'color': 'tertiary',
                    'action': 'confirm', 
                    'next': cls.SIGNING.value[0],
                    'permission': 'coordinators',
                },
                {
                    'title': 'Удалить',
                    'color': 'outline-dark',
                    'action': 'cancel', 
                    'permission': 'coordinators',
                },
            ],
            cls.SIGNING.value[0]: [
                {
                    'title': 'Подписать',
                    'color': 'quaternary',
                    'action': 'confirm', 
                    'next': cls.ACTIVE.value[0],
                    'permission': 'head',
                },
            ],
            cls.ACTIVE.value[0]: [
                {
                    'title': 'В архив',
                    'color': 'outline-muted',
                    'action': 'confirm', 
                    'next': cls.ARCHIVE.value[0],
                    'permission': 'all',
                },
            ],
        }

        return actions.get(status, {})
    