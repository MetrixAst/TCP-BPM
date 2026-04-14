from project.enums import CustomEnum

class DocumentTypeEnum(CustomEnum):
    DOCUMENTS = ("documents", "Документы")
    PURCHASES = ("purchases", "Закупки")
    BUDGET = ("budget", "Бюджет")

    @classmethod
    def get_config(cls, document_type):

        config = {
            cls.DOCUMENTS.value[0]: {
                'id': document_type,
                'title': 'Документооборот',
                'tree': True,
                'add_button': 'Новый документ',
            },
            cls.PURCHASES.value[0]: {
                'id': document_type,
                'title': 'Закупки',
                'tree': True,
                'statuses': True,
                'contractor': True,
                'add_button': 'Новая закупка',
            },
            cls.BUDGET.value[0]: {
                'id': document_type,
                'title': 'Бюджет компании',
                'add_button': 'Добавить документ',
                'hide_left': True,
            },
        }

        return config.get(document_type, None)

class DocumentStatusEnum(CustomEnum):
    DRAFT = ("draft", "Черновик")
    COORDINATION = ("coordination", "Согласование")
    SIGNING = ("signing", "Подписание")
    ACTIVE = ("active", "Действующий")
    ARCHIVE = ("archive", "Архив")

    #PURCHASES
    # OFFER = ("offer", "Новая заявка")
    # MODERATING = ("moderating", "Согласование")
    # COMPLETED = ("completed", "Согласован")
    # REFUSED = ("refused", "Отказано")

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
                'color': 'primary'
            },
            cls.SIGNING.value[0]: {
                'title': cls.SIGNING.value[1],
                'icon': 'edit',
                'color': 'danger'
            },
            cls.ACTIVE.value[0]: {
                'title': cls.ACTIVE.value[1],
                'icon': 'form',
                'color': 'success'
            },
            cls.ARCHIVE.value[0]: {
                'title': cls.ARCHIVE.value[1],
                'icon': 'bin',
                'color': 'muted'
            },
        }

        return full

    @classmethod
    def get_info(cls, status, document_type):
        res = cls.get_full(document_type)

        return res.get(status, {})
    
    @classmethod
    def get_actions(cls, status, document_type):

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
    
    @classmethod
    def get_notification_text(cls, status, document_type):
        res = {
            cls.DRAFT.value[0]: {
                'title': 'Новый документ',
                'text': 'Добавлен новый документ',
            },
            cls.COORDINATION.value[0]: {
                'title': 'Отправлен на согласование',
                'text': 'Документ отправлен на согласование',
            },
            cls.SIGNING.value[0]: {
                'title': 'Отправлен на подпись',
                'text': 'Документ отправлен на подписание',
            },
            cls.ACTIVE.value[0]: {
                'title': 'Новый статус документа',
                'text': 'Документ перемещен в статус "Действующий"',
            },
            cls.ARCHIVE.value[0]: {
                'title': 'Новый статус документа',
                'text': 'Документ отправлен в архив',
            },
        }

        return res.get(status, None)
    