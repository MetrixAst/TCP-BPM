from rest_framework import serializers
from account.models import UserAccount
from .models import Task
from .enums import TaskStatusEnum, PriorityEnum


class UserBriefSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='get_name', read_only=True)

    class Meta:
        model = UserAccount
        fields = ('id', 'username', 'name')


class TaskHistoryEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    status_display = serializers.SerializerMethodField()
    date = serializers.DateTimeField()
    user = serializers.SerializerMethodField()

    def get_status_display(self, obj):
        info = obj.status_info
        return info.get('title', obj.status) if isinstance(info, dict) else obj.status

    def get_user(self, obj):
        if obj.user is None:
            return None
        return obj.user.get_name


class TaskSerializer(serializers.ModelSerializer):
    author = UserBriefSerializer(read_only=True)
    executor = UserBriefSerializer(read_only=True)
    co_executor_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=UserAccount.objects.all(),
        source='co_executors',
        required=False,
    )
    observer_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=UserAccount.objects.all(),
        source='observers',
        required=False,
    )
    status_display = serializers.SerializerMethodField()
    status_color = serializers.SerializerMethodField()
    priority_display = serializers.SerializerMethodField()
    available_actions = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    deleted_at = serializers.DateTimeField(read_only=True)
    deleted_by = UserBriefSerializer(read_only=True)
    deleted_reason = serializers.CharField(read_only=True)
    executor_id = serializers.PrimaryKeyRelatedField(
        queryset=UserAccount.objects.all(),
        source='executor',
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Task
        fields = (
            'id',
            'title',
            'text',
            'status',
            'status_display',
            'status_color',
            'priority',
            'priority_display',
            'deadline',
            'date',
            'views',
            'author',
            'executor',
            'executor_id',
            'co_executor_ids',
            'observer_ids',
            'available_actions',
            'history',
            'deleted_at',
            'deleted_by',
            'deleted_reason',
        )
        read_only_fields = (
            'id',
            'date',
            'views',
            'author',
            'executor',
            'status',
            'status_display',
            'available_actions',
            'deleted_at',
            'deleted_by',
            'deleted_reason',
        )

    def get_status_display(self, obj):
        info = obj.status_info
        return info.get('title', obj.status) if isinstance(info, dict) else obj.status

    def get_status_color(self, obj):
        info = obj.status_info
        return info.get('color', 'neutral') if isinstance(info, dict) else 'neutral'

    def get_priority_display(self, obj):
        labels = dict(PriorityEnum.list())
        return labels.get(obj.priority, obj.priority)

    def get_available_actions(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []
        return obj.actions(request)

    def get_history(self, obj):
        return TaskHistoryEntrySerializer(
            obj.history.all().order_by('-id'), many=True
        ).data

    def create(self, validated_data):
        co_executors = validated_data.pop('co_executors', [])
        observers = validated_data.pop('observers', [])
        request = self.context['request']
        if 'status' not in validated_data:
            validated_data['status'] = TaskStatusEnum.CREATED.value[0]
        if 'priority' not in validated_data:
            validated_data['priority'] = PriorityEnum.MEDIUM.value[0]
        validated_data['author'] = request.user
        task = Task.objects.create(**validated_data)
        if co_executors:
            task.co_executors.set(co_executors)
        if observers:
            task.observers.set(observers)
        task.set_action(request, 'create')
        return task

    def update(self, instance, validated_data):
        co_executors = validated_data.pop('co_executors', None)
        observers = validated_data.pop('observers', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if co_executors is not None:
            instance.co_executors.set(co_executors)
        if observers is not None:
            instance.observers.set(observers)
        return instance