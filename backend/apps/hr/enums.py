from project.enums import CustomEnum
from django.db import models


class CalendarItemType(CustomEnum):
    SECONDMENT = ("secondment", "Командировка")
    VACATION = ("vacation", "Отпуск")

    @classmethod
    def get_title(cls, category):
        res = {
            cls.SECONDMENT.value[0]: 'Командировки',
            cls.VACATION.value[0]: 'Отпуски',
        }

        return res.get(category, '')


class EmployeeStatusEnum(models.TextChoices):
    ACTIVE = 'active', 'Активен'
    DISMISSED = 'dismissed', 'Уволен'
    VACATION = 'vacation', 'В отпуске'
    SICK_LEAVE = 'sick_leave', 'На больничном'


class DayTypeEnum(models.TextChoices):
    WORKING = 'working', 'Рабочий'
    WEEKEND = 'weekend', 'Выходной'
    HOLIDAY = 'holiday', 'Праздник'

class LeaveStatusEnum(models.TextChoices):
    DRAFT = 'draft', 'Черновик'
    PENDING = 'pending', 'На рассмотрении'
    APPROVED = 'approved', 'Одобрено'
    REJECTED = 'rejected', 'Отклонено'
    COMPLETED = 'completed', 'Завершено'