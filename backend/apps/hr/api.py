from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from account.drf_permissions import HrApiPermission
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
