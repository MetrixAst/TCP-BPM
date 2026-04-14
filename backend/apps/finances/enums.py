from project.enums import CustomEnum

class FinanceItemType(CustomEnum):
    INCOME = ("income", "Доход")
    EXPENSE = ("expense", "Расход")