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

class CheckInEnum(models.TextChoices):
    DAY_START = 'day_start', 'Приход (начало дня)'
    LUNCH_START = 'lunch_start', 'Начало обеда'
    LUNCH_END = 'lunch_end', 'Конец обеда'
    DAY_END = 'day_end', 'Уход (конец дня)'

class DocumentTypeEnum(models.TextChoices):
    EMPLOYMENT_CONTRACT = 'employment_contract', 'Трудовой договор'
    NDA = 'nda', 'NDA'
    LIABILITY_AGREEMENT = 'liability_agreement', 'Договор о мат. ответственности'
    OTHER = 'other', 'Другое'

class DocumentStatusEnum(models.TextChoices):
    DRAFT = 'draft', 'Черновик'
    ACTIVE = 'active', 'Активен'
    EXPIRED = 'expired', 'Истёк'
    REVOKED = 'revoked', 'Отозван'

class WorkPermitStatus(models.TextChoices):
    ACTIVE = 'active', 'Активен'
    EXPIRING = 'expiring', 'Истекает'
    EXPIRED = 'expired', 'Просрочен'

class CertificationStatusEnum(models.TextChoices):
    ACTIVE = 'active', 'Активен'
    EXPIRING = 'expiring', 'Истекает'
    EXPIRED = 'expired', 'Истёк'
    REVOKED = 'revoked', 'Отозван'