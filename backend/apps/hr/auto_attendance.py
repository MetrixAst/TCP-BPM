"""Автоотметка: приход/обед/уход по графику для выбранных сотрудников."""
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from .enums import CheckInEnum, DayTypeEnum, EmployeeStatusEnum, LeaveStatusEnum
from .models import AttendanceRecord, EmployeeWorkSchedule, LeaveRequest, WorkCalendar

ON_LEAVE_STATUSES = (LeaveStatusEnum.APPROVED, LeaveStatusEnum.CONFIRMED)


def _is_day_off(employee, day):
    company = employee.department.company if employee.department_id else None
    record = (
        WorkCalendar.objects.filter(company=company, date=day).first()
        or WorkCalendar.objects.filter(company__isnull=True, date=day).first()
    )
    return bool(record and record.day_type != DayTypeEnum.WORKING)


def _on_leave(employee, day):
    return LeaveRequest.objects.filter(
        employee=employee,
        status__in=ON_LEAVE_STATUSES,
        start_date__lte=day,
        end_date__gte=day,
    ).exists()


def _planned_events(schedule):
    events = [(CheckInEnum.DAY_START, schedule.work_start)]
    if schedule.lunch_start and schedule.lunch_end and schedule.lunch_start < schedule.lunch_end:
        events.append((CheckInEnum.LUNCH_START, schedule.lunch_start))
        events.append((CheckInEnum.LUNCH_END, schedule.lunch_end))
    if schedule.work_end > schedule.work_start:
        events.append((CheckInEnum.DAY_END, schedule.work_end))
    disabled = getattr(settings, 'ATTENDANCE_DISABLED_TYPES', [])
    return [(event, at) for event, at in events if event not in disabled]


def run_auto_attendance(now=None):
    """Создаёт недостающие отметки за сегодня, время которых уже наступило.

    Возвращает количество созданных записей.
    """
    now = timezone.localtime(now or timezone.now())
    today = now.date()
    tz = timezone.get_current_timezone()
    created = 0

    schedules = EmployeeWorkSchedule.objects.filter(
        auto_attendance=True,
        employee__status=EmployeeStatusEnum.ACTIVE,
        employee__user__is_active=True,
    ).select_related('employee__department__company')

    for schedule in schedules:
        employee = schedule.employee
        if not schedule.is_workday(today) or _is_day_off(employee, today) or _on_leave(employee, today):
            continue

        existing = set(
            AttendanceRecord.objects.filter(employee=employee, timestamp__date=today)
            .values_list('event_type', flat=True)
        )
        for event, at in _planned_events(schedule):
            if event in existing:
                continue
            moment = timezone.make_aware(datetime.combine(today, at), tz)
            if moment > now:
                continue
            AttendanceRecord.objects.create(
                employee=employee,
                event_type=event,
                timestamp=moment,
                source=AttendanceRecord.SOURCE_AUTO,
            )
            existing.add(event)
            created += 1
    return created
