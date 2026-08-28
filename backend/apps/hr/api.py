from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from account.drf_permissions import HrApiPermission, HROrAdminPermission
from account.models import Employee, Department
from audit.models import AuditLog
from audit.services import diff_instances, log_event

from .models import Company
from .serializers import CompanySerializer, DepartmentSerializer, EmployeeSerializer, AttendanceRecordSerializer
from hr.models import AttendanceRecord



class CompanyFilter(filters.FilterSet):
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')
    bin_number = filters.CharFilter(field_name='bin_number', lookup_expr='icontains')

    class Meta:
        model = Company
        fields = ['name', 'bin_number']


class DepartmentFilter(filters.FilterSet):
    company = filters.NumberFilter(field_name='company_id')
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')
    parent = filters.NumberFilter(field_name='parent_id')

    class Meta:
        model = Department
        fields = ['company', 'name', 'parent']


class EmployeeFilter(filters.FilterSet):
    department = filters.NumberFilter(field_name='department_id')
    status = filters.CharFilter(field_name='status')
    company = filters.NumberFilter(field_name='department__company_id')

    class Meta:
        model = Employee
        fields = ['department', 'status', 'company']


class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all().order_by('name')
    serializer_class = CompanySerializer
    permission_classes = [HrApiPermission]
    filterset_class = CompanyFilter
    search_fields = ['name', 'bin_number']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.select_related('company', 'parent').order_by('tree_id', 'lft')
    serializer_class = DepartmentSerializer
    permission_classes = [HrApiPermission]
    filterset_class = DepartmentFilter
    search_fields = ['name']
    ordering_fields = ['name', 'tree_id']
    ordering = ['tree_id', 'lft']

    def perform_create(self, serializer):
        department = serializer.save()
        log_event(
            AuditLog.Action.CREATE,
            instance=department,
            user=self.request.user,
        )

    def perform_update(self, serializer):
        old = Department.objects.get(pk=serializer.instance.pk)
        department = serializer.save()
        changes = diff_instances(old, department)
        if changes:
            log_event(
                AuditLog.Action.UPDATE,
                instance=department,
                changes=changes,
                user=self.request.user,
            )

    def perform_destroy(self, instance):
        if instance.employees.exists():
            raise ValidationError(
                'Нельзя удалить отдел: в нём есть сотрудники. Переведите их в другой отдел.',
            )
        if instance.get_children().exists():
            raise ValidationError(
                'Нельзя удалить отдел: сначала удалите или переместите дочерние отделы.',
            )
        log_event(
            AuditLog.Action.DELETE,
            instance=instance,
            user=self.request.user,
        )
        instance.delete()

    @action(detail=False, methods=['get'], url_path='tree')
    def tree(self, request):
        qs = self.filter_queryset(self.get_queryset())
        company_id = request.query_params.get('company')
        if company_id:
            qs = qs.filter(company_id=company_id)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related(
        'user',
        'department',
        'department__company',
        'position',
        'supervisor',
    ).order_by('-head', 'user__last_name')
    serializer_class = EmployeeSerializer
    permission_classes = [HrApiPermission]
    filterset_class = EmployeeFilter
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'iin']
    ordering_fields = ['id', 'hire_date', 'status']
    ordering = ['-head', 'user__last_name']

    @action(detail=True, methods=['post'], url_path='deactivate')
    def deactivate(self, request, pk=None):
        employee = self.get_object()
        reason = request.data.get('reason', '').strip()
        if len(reason) < 5:
            return Response(
                {'detail': 'Причина деактивации обязательна (минимум 5 символов).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        old_status = employee.status
        employee.status = 'dismissed'
        employee.save(update_fields=['status'])

        ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
        from account.models import EmployeeStatusLog
        EmployeeStatusLog.objects.create(
            employee=employee,
            actor=request.user,
            old_status=old_status,
            new_status='dismissed',
            reason=reason,
            ip_address=ip,
        )
        return Response(EmployeeSerializer(employee).data)


    @action(detail=True, methods=['post'], url_path='activate')
    def activate(self, request, pk=None):
        employee = self.get_object()
        reason = request.data.get('reason', '').strip()
        old_status = employee.status
        employee.status = 'active'
        employee.save(update_fields=['status'])

        ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
        from account.models import EmployeeStatusLog
        EmployeeStatusLog.objects.create(
            employee=employee,
            actor=request.user,
            old_status=old_status,
            new_status='active',
            reason=reason,
            ip_address=ip,
        )
        return Response(EmployeeSerializer(employee).data)


    @action(detail=False, methods=['post'], url_path='batch-status')
    def batch_status(self, request):
        employee_ids = request.data.get('employee_ids', [])
        action_type = request.data.get('action', '')
        reason = request.data.get('reason', '').strip()

        if not isinstance(employee_ids, list) or not employee_ids:
            return Response({'detail': 'employee_ids обязателен.'}, status=status.HTTP_400_BAD_REQUEST)
        if action_type not in ('activate', 'deactivate'):
            return Response({'detail': 'action должен быть activate или deactivate.'}, status=status.HTTP_400_BAD_REQUEST)
        if action_type == 'deactivate' and len(reason) < 5:
            return Response({'detail': 'Причина деактивации обязательна.'}, status=status.HTTP_400_BAD_REQUEST)

        new_status = 'active' if action_type == 'activate' else 'dismissed'
        employees = Employee.objects.filter(id__in=employee_ids)

        ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
        from account.models import EmployeeStatusLog

        logs = []
        for emp in employees:
            old_status = emp.status
            emp.status = new_status
            emp.save(update_fields=['status'])
            logs.append(EmployeeStatusLog(
                employee=emp,
                actor=request.user,
                old_status=old_status,
                new_status=new_status,
                reason=reason,
                ip_address=ip,
            ))
        EmployeeStatusLog.objects.bulk_create(logs)

        return Response({
            'updated': len(employees),
            'action': action_type,
            'employee_ids': list(employees.values_list('id', flat=True)),
        })

class ManualAttendanceViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AttendanceRecordSerializer

    def get_permissions(self):
        from account.drf_permissions import HROrAdminPermission
        return [HROrAdminPermission()]

    def get_queryset(self):
        return AttendanceRecord.objects.filter(is_manual=True).select_related(
            'employee', 'manual_author', 'manual_reason'
        ).order_by('-timestamp')

    def _get_ip(self, request):
        return request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')

    def _record_snapshot(self, record):
        return {
            'event_type': record.event_type,
            'timestamp': record.timestamp.isoformat(),
            'manual_comment': record.manual_comment,
            'manual_reason_id': record.manual_reason_id,
        }

    def perform_create(self, serializer):
        from hr.models import AttendanceEditLog
        record = serializer.save(
            is_manual=True,
            manual_author=self.request.user,
        )
        AttendanceEditLog.objects.create(
            record=record,
            actor=self.request.user,
            action='create',
            before=None,
            after=self._record_snapshot(record),
            ip_address=self._get_ip(self.request),
        )

    def perform_update(self, serializer):
        from hr.models import AttendanceEditLog
        before = self._record_snapshot(serializer.instance)
        record = serializer.save()
        AttendanceEditLog.objects.create(
            record=record,
            actor=self.request.user,
            action='update',
            before=before,
            after=self._record_snapshot(record),
            ip_address=self._get_ip(self.request),
        )

    def perform_destroy(self, instance):
        from hr.models import AttendanceEditLog
        AttendanceEditLog.objects.create(
            record=instance,
            actor=self.request.user,
            action='delete',
            before=self._record_snapshot(instance),
            after=None,
            ip_address=self._get_ip(self.request),
        )
        instance.delete()

    @action(detail=True, methods=['get'], url_path='history')
    def history(self, request, pk=None):
        from hr.models import AttendanceEditLog
        record = self.get_object()
        logs = AttendanceEditLog.objects.filter(record=record).select_related('actor').order_by('-id')
        data = [{
            'id': log.id,
            'action': log.action,
            'action_display': dict(AttendanceEditLog._meta.get_field('action').choices).get(log.action, log.action),
            'actor': log.actor.get_name if log.actor else None,
            'before': log.before,
            'after': log.after,
            'ip_address': log.ip_address,
            'created_at': log.created_at.isoformat(),
        } for log in logs]
        return Response({'results': data})


class AttendanceReportViewSet(viewsets.ViewSet):

    def get_permissions(self):
        return [HROrAdminPermission()]

    def list(self, request):
        from datetime import date, timedelta
        from django.utils import timezone
        from hr.models import AttendanceRecord
        from account.models import Employee

        date_from_str = request.query_params.get('date_from')
        date_to_str = request.query_params.get('date_to')
        employee_id = request.query_params.get('employee_id')
        author_id = request.query_params.get('author_id')

        date_from = date.fromisoformat(date_from_str) if date_from_str else date.today() - timedelta(days=30)
        date_to = date.fromisoformat(date_to_str) if date_to_str else date.today()

        employees = Employee.objects.filter(status='active').select_related('user', 'department')
        if employee_id:
            employees = employees.filter(pk=employee_id)

        report = []
        for emp in employees:
            records = AttendanceRecord.objects.filter(
                employee=emp,
                timestamp__date__gte=date_from,
                timestamp__date__lte=date_to,
            )
            if author_id:
                records = records.filter(manual_author_id=author_id)

            manual_records = records.filter(is_manual=True)
            auto_records = records.filter(is_manual=False)

            total_manual = manual_records.count()
            total_auto = auto_records.count()

            total_work_time_seconds = 0
            current = date_from
            while current <= date_to:
                summary = AttendanceRecord.get_daily_summary(emp, current)
                total_work_time_seconds += summary['total_work_time'].total_seconds()
                current += timedelta(days=1)

            report.append({
                'employee_id': emp.pk,
                'employee_name': emp.user.get_name,
                'department': emp.department.name if emp.department else None,
                'total_records': total_manual + total_auto,
                'manual_records': total_manual,
                'auto_records': total_auto,
                'total_work_hours': round(total_work_time_seconds / 3600, 2),
                'period': {
                    'date_from': date_from.isoformat(),
                    'date_to': date_to.isoformat(),
                },
            })

        export = request.query_params.get('export')
        if export == 'xlsx':
            return self._export_xlsx(report, date_from, date_to)

        return Response(report)

    def _export_xlsx(self, report, date_from, date_to):
        import openpyxl
        from django.http import HttpResponse

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Отчёт по отметкам"

        headers = [
            'Сотрудник', 'Отдел', 'Всего отметок',
            'Ручных', 'Автоматических', 'Рабочих часов'
        ]
        ws.append(headers)

        for row in report:
            ws.append([
                row['employee_name'],
                row['department'] or '-',
                row['total_records'],
                row['manual_records'],
                row['auto_records'],
                row['total_work_hours'],
            ])

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="attendance_report_{date_from}_{date_to}.xlsx"'
        wb.save(response)
        return response

class AttendanceRegistryViewSet(viewsets.ViewSet):
    def get_permissions(self):
        from account.drf_permissions import AttendanceRegistryPermission
        return [AttendanceRegistryPermission()]

    def _get_allowed_employees(self, request):
        from account.role_permissions import RoleEnums
        from account.models import Employee, Department
        user = request.user
        role = getattr(user, 'role', None)

        if role in [
            RoleEnums.ADMINISTRATOR.value,
            RoleEnums.HR.value,
            RoleEnums.OWNER.value,
            RoleEnums.CFO.value,
            RoleEnums.CHIEF_ACCOUNTANT.value,
        ]:
            return Employee.objects.filter(status='active').select_related('user', 'department')

        employee = getattr(user, 'employee_info', None)
        if employee and getattr(employee, 'head', False) and employee.department_id:
            dept_ids = list(
                employee.department.get_descendants(include_self=True).values_list('id', flat=True)
            )
            return Employee.objects.filter(
                department_id__in=dept_ids, status='active'
            ).select_related('user', 'department')

        return Employee.objects.none()

    def list(self, request):
        from datetime import date, timedelta, datetime
        from hr.models import AttendanceRecord
        from django.utils import timezone as tz

        date_from_str = request.query_params.get('date_from')
        date_to_str = request.query_params.get('date_to')
        employee_id = request.query_params.get('employee_id')
        department_id = request.query_params.get('department_id')

        date_from = date.fromisoformat(date_from_str) if date_from_str else date.today() - timedelta(days=30)
        date_to = date.fromisoformat(date_to_str) if date_to_str else date.today()

        employees = self._get_allowed_employees(request)

        if employee_id:
            employees = employees.filter(pk=employee_id)
        if department_id:
            employees = employees.filter(department_id=department_id)

        result = []
        current = date_from
        while current <= date_to:
            for emp in employees:
                records = AttendanceRecord.objects.filter(
                    employee=emp,
                    timestamp__date=current,
                ).order_by('timestamp')

                day_start = records.filter(event_type='day_start').first()
                day_end = records.filter(event_type='day_end').last()

                sources = list(records.values_list('source', flat=True).distinct())
                source = sources[0] if len(sources) == 1 else 'mixed' if sources else None

                summary = AttendanceRecord.get_daily_summary(emp, current)
                total_hours = round(summary['total_work_time'].total_seconds() / 3600, 2)

                result.append({
                    'date': current.isoformat(),
                    'employee_id': emp.pk,
                    'employee_name': emp.user.get_name,
                    'department': emp.department.name if emp.department else None,
                    'day_start': day_start.timestamp.isoformat() if day_start else None,
                    'day_end': day_end.timestamp.isoformat() if day_end else None,
                    'total_hours': total_hours,
                    'source': source,
                    'is_complete': summary['is_complete'],
                })
            current += timedelta(days=1)

        export = request.query_params.get('export')
        if export == 'xlsx':
            return self._export_xlsx(result, date_from, date_to)

        return Response(result)

    def _export_xlsx(self, data, date_from, date_to):
        import openpyxl
        from django.http import HttpResponse

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Реестр посещаемости'
        ws.append(['Дата', 'Сотрудник', 'Отдел', 'Приход', 'Уход', 'Часов', 'Источник'])

        for row in data:
            ws.append([
                row['date'],
                row['employee_name'],
                row['department'] or '-',
                row['day_start'] or '-',
                row['day_end'] or '-',
                row['total_hours'],
                row['source'] or '-',
            ])

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="attendance_{date_from}_{date_to}.xlsx"'
        wb.save(response)
        return response
