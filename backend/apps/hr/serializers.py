from datetime import timedelta

from rest_framework import serializers

from account.models import Employee, Department, UserAccount
from .models import CalendarItem, Company
from .enums import CalendarItemType

_CALENDAR_EVENT_STYLE = {
    CalendarItemType.SECONDMENT.value[0]: {
        'backgroundColor': '#2563eb',
        'borderColor': '#1d4ed8',
        'className': 'hr-cal-event hr-cal-event--secondment',
    },
    CalendarItemType.VACATION.value[0]: {
        'backgroundColor': '#16a34a',
        'borderColor': '#15803d',
        'className': 'hr-cal-event hr-cal-event--vacation',
    },
}


class CalendarItemSerializer(serializers.ModelSerializer):

    category = serializers.SerializerMethodField()
    start = serializers.SerializerMethodField()
    end = serializers.SerializerMethodField()
    allDay = serializers.SerializerMethodField()
    backgroundColor = serializers.SerializerMethodField()
    borderColor = serializers.SerializerMethodField()
    className = serializers.SerializerMethodField()
    extendedProps = serializers.SerializerMethodField()

    def get_category(self, obj):
        return CalendarItemType.from_value(obj.category)[1]

    def get_user(self, obj):
        return obj.user.get_name if obj.user else None

    def get_title(self, obj):
        name = obj.user.get_name if obj.user else ''
        if obj.title:
            return f'{obj.title}, {name}' if name else obj.title
        return name or 'Командировка'

    def get_start(self, obj):
        return obj.start_date.isoformat()

    def get_end(self, obj):
        return (obj.end_date + timedelta(days=1)).isoformat()

    def get_allDay(self, obj):
        return True

    def _style(self, obj):
        return _CALENDAR_EVENT_STYLE.get(obj.category, _CALENDAR_EVENT_STYLE[CalendarItemType.VACATION.value[0]])

    def get_backgroundColor(self, obj):
        return self._style(obj)['backgroundColor']

    def get_borderColor(self, obj):
        return self._style(obj)['borderColor']

    def get_className(self, obj):
        return self._style(obj)['className']

    def get_extendedProps(self, obj):
        return {
            'category': self.get_category(obj),
            'eventType': obj.category,
            'user': self.get_user(obj),
        }

    user = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()

    class Meta:
        model = CalendarItem
        fields = (
            'id', 'user', 'title', 'start', 'end', 'category',
            'allDay', 'backgroundColor', 'borderColor', 'className', 'extendedProps',
        )


class CompanySerializer(serializers.ModelSerializer):
    employees_count = serializers.IntegerField(source='get_employees_count', read_only=True)

    class Meta:
        model = Company
        fields = (
            'id',
            'name',
            'bin_number',
            'address',
            'phone',
            'email',
            'created_at',
            'employees_count',
        )
        read_only_fields = ('id', 'created_at', 'employees_count')


class DepartmentSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    parent_name = serializers.CharField(source='parent.name', read_only=True, allow_null=True)
    employees_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = (
            'id',
            'name',
            'company',
            'company_name',
            'parent',
            'parent_name',
            'level_type',
            'employees_count',
            'lft',
            'rght',
            'tree_id',
            'level',
        )
        read_only_fields = ('lft', 'rght', 'tree_id', 'level', 'employees_count')

    def get_employees_count(self, obj):
        return obj.employees.count()

    def validate(self, attrs):
        parent = attrs.get('parent')
        company = attrs.get('company')
        instance = getattr(self, 'instance', None)

        if instance is not None:
            if parent is None and 'parent' not in attrs:
                parent = instance.parent
            if company is None and 'company' not in attrs:
                company = instance.company

        if parent and company and parent.company_id != company.id:
            raise serializers.ValidationError({
                'parent': 'Родительский отдел должен принадлежать той же компании.',
            })

        if instance and parent:
            if parent.pk == instance.pk:
                raise serializers.ValidationError({
                    'parent': 'Отдел не может быть родителем самого себя.',
                })
            descendant_ids = instance.get_descendants(include_self=True).values_list('pk', flat=True)
            if parent.pk in descendant_ids:
                raise serializers.ValidationError({
                    'parent': 'Нельзя переместить отдел внутрь своего поддерева.',
                })

        name = attrs.get('name')
        if name and company:
            qs = Department.objects.filter(company=company, name=name)
            if instance:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    'name': 'Отдел с таким названием уже есть в этой компании.',
                })

        return attrs


class EmployeeSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    full_name = serializers.CharField(source='user.get_name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    position_title = serializers.CharField(
        source='position.title',
        read_only=True,
        allow_null=True,
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Employee
        fields = (
            'id',
            'user',
            'username',
            'full_name',
            'iin',
            'status',
            'status_display',
            'hire_date',
            'phone',
            'personal_email',
            'department',
            'department_name',
            'position',
            'position_title',
            'supervisor',
            'head',
        )
        read_only_fields = ('id', 'username', 'full_name', 'department_name', 'position_title', 'status_display')
