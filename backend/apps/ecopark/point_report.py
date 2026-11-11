"""Отчёт по помещению для руководителя — то, что он видит, отсканировав QR."""


def _employee_name(employee):
    user = employee.user
    return user.get_full_name() or user.username


def build_point_report(point, recent_limit=10, defects_limit=20):
    from .models import Defect

    slots = point.checklist_slots()
    recent = (
        point.visits
        .select_related('employee__user', 'checklist')
        .prefetch_related('answers')
        .order_by('-created_at')[:recent_limit]
    )
    open_defects = (
        point.defects
        .exclude(status=Defect.STATUS_RESOLVED)
        .select_related('reported_by__user', 'visit__checklist')
        .order_by('-created_at')[:defects_limit]
    )

    return {
        'point_uuid': str(point.uuid),
        'point_name': point.name,
        'location': point.location,
        'is_overdue': any(slot['is_overdue'] for slot in slots),
        'checklists': [{
            'checklist_name': slot['checklist'].name if slot['checklist'] else None,
            'assignee': slot['assignee'],
            'interval_hours': slot['interval_hours'],
            'is_overdue': slot['is_overdue'],
            'last_visit_at': slot['last_visit'].created_at.isoformat() if slot['last_visit'] else None,
            'last_visit_by': _employee_name(slot['last_visit'].employee) if slot['last_visit'] else None,
        } for slot in slots],
        'open_defects': [{
            'id': defect.pk,
            'description': defect.description,
            # По какому чек-листу записана: электрика, сантехника, клининг…
            'checklist_name': defect.visit.checklist.name if defect.visit.checklist else None,
            'priority': defect.priority,
            'status': defect.status,
            'created_at': defect.created_at.isoformat(),
            'reported_by': _employee_name(defect.reported_by) if defect.reported_by else None,
        } for defect in open_defects],
        'recent_visits': [{
            'id': visit.pk,
            'created_at': visit.created_at.isoformat(),
            'employee_name': _employee_name(visit.employee),
            'checklist_name': visit.checklist.name if visit.checklist else None,
            'failed_count': sum(1 for a in visit.answers.all() if not a.passed),
            'comment': visit.comment,
        } for visit in recent],
    }
