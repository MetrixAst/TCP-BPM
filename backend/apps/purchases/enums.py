from project.enums import CustomEnum

class SupplierStatusEnum(CustomEnum):
    MODERATED = ("moderated", "На модерации")
    CHECKED = ("checked", "Проверен")
    REFUSED = ("refused", "Отказано")

    @classmethod
    def get_color(cls, status):
        statuses = {
            cls.MODERATED.value[0]: "warning",
            cls.CHECKED.value[0]: "success",
            cls.REFUSED.value[0]: "danger",
        }

        return statuses.get(status, '')


class SupplierCheckedStatusEnum(CustomEnum):
    RELIABLE = ("reliable", "Благонадежный")
    UNRELIABLE = ("reliable", "Неблагонадежный")


class SupplierFormEnum(CustomEnum):
    TOO = ("too", "ТОО")
    IP = ("ip", "ИП")


class SupplierTypeEnum(CustomEnum):
    INDIVIDUAL = ("individual", "Физ. лицо")
    LEGAL = ("legal", "Юр. лицо")
