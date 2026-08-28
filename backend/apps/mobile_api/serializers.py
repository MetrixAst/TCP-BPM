from rest_framework import serializers

from tickets.models import ServiceRequest, TicketAttachment
from hr.enums import CheckInEnum
from tickets.models import TicketMessage
from account.models import Notification
from tenants.models import Room

class NotificationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    text = serializers.CharField()
    created_date = serializers.DateTimeField()
    target_type = serializers.CharField(allow_null=True)
    target_id = serializers.IntegerField(allow_null=True)
    url = serializers.CharField(allow_null=True)
    is_read = serializers.SerializerMethodField()

    def get_is_read(self, obj):
        unread_target_ids = self.context.get('unread_targets', set())
        key = (obj.target_type, obj.target_id)
        return key not in unread_target_ids

class TicketMessageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    author = serializers.SerializerMethodField()
    text = serializers.CharField()
    created_at = serializers.DateTimeField()

    def get_author(self, obj):
        if obj.author is None:
            return None
        return {
            'id': obj.author.id,
            'full_name': obj.author.get_name,
        }


class TicketMessageCreateSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000)

class TicketAttachmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    file = serializers.SerializerMethodField()
    original_name = serializers.CharField()
    created_at = serializers.DateTimeField()

    def get_file(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class ServiceRequestListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    number = serializers.CharField()
    title = serializers.CharField()
    category = serializers.CharField()
    priority = serializers.CharField()
    status = serializers.CharField()
    room = serializers.CharField(allow_blank=True, allow_null=True)
    created_at = serializers.DateTimeField()
    photo = serializers.SerializerMethodField()

    def get_photo(self, obj):
        request = self.context.get('request')
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        return None


class ServiceRequestDetailSerializer(ServiceRequestListSerializer):
    description = serializers.CharField()
    updated_at = serializers.DateTimeField()
    attachments = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()

    def get_attachments(self, obj):
        return TicketAttachmentSerializer(
            obj.attachments.all(), many=True, context=self.context
        ).data

    def get_history(self, obj):
        return ServiceRequestHistoryEntrySerializer(
            obj.history.all(), many=True
        ).data


class ServiceRequestCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    description = serializers.CharField(max_length=3000)
    category = serializers.ChoiceField(choices=ServiceRequest.CATEGORIES)
    priority = serializers.ChoiceField(choices=ServiceRequest.PRIORITIES, required=False)
    room = serializers.CharField(max_length=60, required=False, allow_blank=True)
    photo = serializers.ImageField(required=False, allow_null=True)


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

class ServiceRequestHistoryEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    comment = serializers.CharField(allow_null=True, allow_blank=True)
    created_at = serializers.DateTimeField()
    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        if obj.user is None:
            return None
        return obj.user.get_name

class RoomResolveSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    number = serializers.CharField()
    map_id = serializers.CharField()
    floor = serializers.IntegerField()