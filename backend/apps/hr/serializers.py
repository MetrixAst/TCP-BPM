from rest_framework import serializers

from account.models import Employee, Department, UserAccount
from .models import CalendarItem, Company
from .enums import CalendarItemType


class CalendarItemSerializer(serializers.ModelSerializer):

    category = serializers.SerializerMethodField()

    def get_category(self, obj):
        return CalendarItemType.from_value(obj.category)[1]

    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        return obj.user.get_name if obj.user else None

    title = serializers.SerializerMethodField()

    def get_title(self, obj):
        if obj.user:
            return f"{obj.title}, {obj.user.get_name}"
        return obj.title

    class Meta:
        model = CalendarItem
        fields = ('id', 'user', 'title', 'start', 'end', 'category',)


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
            'lft',
            'rght',
            'tree_id',
            'level',
        )
        read_only_fields = ('lft', 'rght', 'tree_id', 'level')


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
