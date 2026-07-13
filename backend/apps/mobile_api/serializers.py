from rest_framework import serializers
from hr.enums import CheckInEnum


class EmployeeInfoSerializer(serializers.Serializer):
    department = serializers.SerializerMethodField()
    position = serializers.SerializerMethodField()
    status = serializers.CharField()
    phone = serializers.CharField()
    hire_date = serializers.DateField(allow_null=True)
    head = serializers.BooleanField()

    def get_department(self, obj):
        return obj.department.name if obj.department_id else None

    def get_position(self, obj):
        return obj.position.title if obj.position_id else None


class ProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField(source='get_name')
    role = serializers.CharField()
    email = serializers.EmailField()
    avatar = serializers.SerializerMethodField()
    employee = serializers.SerializerMethodField()

    def get_avatar(self, obj):
        return obj.get_avatar_url()

    def get_employee(self, obj):
        info = obj.get_info()
        if info is None:
            return None
        return EmployeeInfoSerializer(info).data


class PushTokenSerializer(serializers.Serializer):
    fcm = serializers.CharField(max_length=230)


class AttendanceCheckinSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=CheckInEnum.choices)
    photo = serializers.ImageField()
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)


class AttendanceRecordOutSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    event_type = serializers.CharField()
    timestamp = serializers.DateTimeField()
    location_address = serializers.CharField()