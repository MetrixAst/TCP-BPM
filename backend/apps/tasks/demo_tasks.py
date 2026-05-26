"""Демо-задачи для менеджера задач и главного дашборда."""

from datetime import timedelta

from django.utils import timezone

from .enums import PriorityEnum, TaskStatusEnum, TaskTypeEnum

# (title, text, status, priority, task_type, days_until_deadline)
DEMO_TASKS = [
    (
        'Подготовить сводку по дебиторке арендаторов',
        'Собрать задолженность по реестру оплат за текущий месяц для финансового дашборда.',
        TaskStatusEnum.CREATED.value[0],
        PriorityEnum.HIGH.value[0],
        TaskTypeEnum.ASSIGNMENT.value[0],
        5,
    ),
    (
        'Согласовать договор аренды — помещение 214',
        'Проверить условия продления и направить на подпись юристу.',
        TaskStatusEnum.ACCEPTED.value[0],
        PriorityEnum.MEDIUM.value[0],
        TaskTypeEnum.APPROVAL.value[0],
        7,
    ),
    (
        'Сверить контрагентов BPM с выгрузкой 1С',
        'Убедиться, что новые поставщики из закупок есть в справочнике 1С.',
        TaskStatusEnum.COMPLETED.value[0],
        PriorityEnum.MEDIUM.value[0],
        TaskTypeEnum.ASSIGNMENT.value[0],
        -2,
    ),
    (
        'Проверить журнал посещаемости за неделю',
        'Выборочно сверить фото check-in и время с табелем HR.',
        TaskStatusEnum.CREATED.value[0],
        PriorityEnum.LOW.value[0],
        TaskTypeEnum.ASSIGNMENT.value[0],
        3,
    ),
    (
        'Утвердить платёжный календарь на июнь',
        'Согласовать плановые даты с CFO и внести правки при необходимости.',
        TaskStatusEnum.ACCEPTED.value[0],
        PriorityEnum.HIGH.value[0],
        TaskTypeEnum.APPROVAL.value[0],
        4,
    ),
    (
        'Доработать отчёт для собственника ТРЦ',
        'Добавить блок по трафику и конверсии в раздел «Показатели».',
        TaskStatusEnum.REVISION.value[0],
        PriorityEnum.MEDIUM.value[0],
        TaskTypeEnum.DOCUMENT.value[0],
        6,
    ),
    (
        'Запросить КП на клининг 2-го этажа',
        'Получить три коммерческих предложения и выложить в папку «Тендерная документация».',
        TaskStatusEnum.CREATED.value[0],
        PriorityEnum.MEDIUM.value[0],
        TaskTypeEnum.ASSIGNMENT.value[0],
        10,
    ),
    (
        'Обновить оргструктуру после перевода',
        'Внести изменения по отделу эксплуатации в HR.',
        TaskStatusEnum.REJECTED.value[0],
        PriorityEnum.LOW.value[0],
        TaskTypeEnum.ASSIGNMENT.value[0],
        1,
    ),
    (
        'Подготовить счёт арендатору Magnum',
        'Сформировать счёт в BPM и отправить на email контрагента.',
        TaskStatusEnum.ACCEPTED.value[0],
        PriorityEnum.CRITICAL.value[0],
        TaskTypeEnum.DOCUMENT.value[0],
        2,
    ),
]
