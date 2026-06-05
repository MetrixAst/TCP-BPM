"""Помощники для работы с персональным графиком сотрудника."""

from datetime import time

DEFAULT_START = time(9, 0)


def get_schedule(employee):
    """Вернуть график сотрудника или None (reverse OneToOne бросает исключение)."""
    if employee is None:
        return None
    try:
        return employee.work_schedule
    except Exception:
        return None


def late_threshold(employee):
    """Время, позже которого приход считается опозданием (с учётом графика)."""
    schedule = get_schedule(employee)
    if schedule is None:
        return DEFAULT_START
    return schedule.start_with_grace()


def is_late(employee, local_start_dt):
    """local_start_dt — datetime прихода в локальной TZ."""
    if local_start_dt is None:
        return False
    return local_start_dt.time() > late_threshold(employee)
