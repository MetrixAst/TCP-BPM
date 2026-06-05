from django_filters import rest_framework as filters
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from account.drf_permissions import HrApiPermission
from account.models import Employee, Department
from audit.models import AuditLog
from audit.services import diff_instances, log_event

from .models import Company
from .serializers import CompanySerializer, DepartmentSerializer, EmployeeSerializer


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
        """Плоский список отделов для селектов и редактора оргструктуры."""
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
