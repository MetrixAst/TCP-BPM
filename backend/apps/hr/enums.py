from project.enums import CustomEnum

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