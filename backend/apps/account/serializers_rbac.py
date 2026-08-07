from rest_framework import serializers

from account.models import UserAccount
from account.models_rbac import AppPermission, PermissionProfile, UserPermissionOverride, ProfileAssignment


class AppPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppPermission
        fields = ['id', 'code', 'category', 'label', 'is_active', 'block', 'operation']


class PermissionProfileSerializer(serializers.ModelSerializer):
    permissions = AppPermissionSerializer(many=True, read_only=True)
    permission_ids = serializers.PrimaryKeyRelatedField(
        source='permissions',
        many=True,
        queryset=AppPermission.objects.filter(is_active=True),
        write_only=True,
        required=False,
    )

    class Meta:
        model = PermissionProfile
        fields = [
            'id', 'name', 'role', 'is_system', 'description',
            'permissions', 'permission_ids',
        ]

    def update(self, instance, validated_data):
        perms = validated_data.pop('permissions', None)
        instance = super().update(instance, validated_data)
        if perms is not None:
            instance.permissions.set(perms)
        return instance

    def create(self, validated_data):
        perms = validated_data.pop('permissions', None)
        instance = super().create(validated_data)
        if perms is not None:
            instance.permissions.set(perms)
        return instance


class UserPermissionOverrideSerializer(serializers.ModelSerializer):
    permission_code = serializers.SlugRelatedField(
        source='permission',
        slug_field='code',
        queryset=AppPermission.objects.filter(is_active=True),
    )
    permission_label = serializers.CharField(source='permission.label', read_only=True)

    class Meta:
        model = UserPermissionOverride
        fields = ['id', 'permission_code', 'permission_label', 'effect', 'reason', 'created_by', 'created_at']
        read_only_fields = ['id', 'permission_label', 'created_by', 'created_at']

    def validate(self, attrs):
        user = self.context['user']
        perm = attrs['permission']
        qs = UserPermissionOverride.objects.filter(user=user, permission=perm)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Переопределение для права '{perm.code}' уже существует."
            )
        return attrs

    def create(self, validated_data):
        validated_data['user'] = self.context['user']
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class UserMatrixSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_name', read_only=True)
    overrides = serializers.SerializerMethodField()
    role_permissions = serializers.SerializerMethodField()
    department_id = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    employee_status = serializers.SerializerMethodField()

    class Meta:
        model = UserAccount
        fields = [
            'id', 'username', 'full_name', 'role',
            'department_id', 'department_name', 'employee_status',
            'overrides', 'role_permissions',
        ]

    def get_overrides(self, obj):
        qs = obj.permission_overrides.select_related('permission').all()
        return UserPermissionOverrideSerializer(qs, many=True, read_only=True).data

    def get_role_permissions(self, obj):
        try:
            profile = PermissionProfile.objects.get(role=obj.role)
            return list(profile.permissions.filter(is_active=True).values_list('code', flat=True))
        except PermissionProfile.DoesNotExist:
            return []

    def get_department_id(self, obj):
        emp = obj.get_info()
        return emp.department_id if emp else None

    def get_department_name(self, obj):
        emp = obj.get_info()
        return emp.department.name if emp and emp.department_id else None

    def get_employee_status(self, obj):
        emp = obj.get_info()
        return emp.status if emp else None


class UserListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_name', read_only=True)
    override_count = serializers.IntegerField(read_only=True)
    department_id = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    employee_status = serializers.SerializerMethodField()

    class Meta:
        model = UserAccount
        fields = [
            'id', 'username', 'full_name', 'role',
            'department_id', 'department_name', 'employee_status',
            'override_count',
        ]

    def get_department_id(self, obj):
        emp = obj.get_info()
        return emp.department_id if emp else None

    def get_department_name(self, obj):
        emp = obj.get_info()
        return emp.department.name if emp and emp.department_id else None

    def get_employee_status(self, obj):
        emp = obj.get_info()
        return emp.status if emp else None

class ProfileAssignmentSerializer(serializers.ModelSerializer):
    profile_name = serializers.CharField(source='profile.name', read_only=True)
    department_name = serializers.SerializerMethodField()

    class Meta:
        model = ProfileAssignment
        fields = [
            'id', 'profile', 'profile_name',
            'scope_type', 'role', 'department', 'department_name',
            'can_delegate', 'assigned_by', 'assigned_at',
        ]
        read_only_fields = ['id', 'profile_name', 'department_name', 'assigned_by', 'assigned_at']

    def get_department_name(self, obj):
        return obj.department.name if obj.department else None

    def validate(self, attrs):
        scope_type = attrs.get('scope_type')
        role = attrs.get('role')
        department = attrs.get('department')

        if scope_type == ProfileAssignment.SCOPE_ROLE:
            if not role:
                raise serializers.ValidationError(
                    {'role': 'Обязательно для scope_type=role.'}
                )
            if department:
                raise serializers.ValidationError(
                    {'department': 'Должно быть пустым для scope_type=role.'}
                )

        elif scope_type == ProfileAssignment.SCOPE_DEPARTMENT:
            if not department:
                raise serializers.ValidationError(
                    {'department': 'Обязательно для scope_type=department.'}
                )
            if role:
                raise serializers.ValidationError(
                    {'role': 'Должно быть пустым для scope_type=department.'}
                )

        return attrs

    def create(self, validated_data):
        validated_data['assigned_by'] = self.context['request'].user
        return super().create(validated_data)


class DelegationSerializer(serializers.Serializer):
    target_user_id = serializers.IntegerField()
    permission_codes = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
    )
    effect = serializers.ChoiceField(choices=UserPermissionOverride.EFFECT_CHOICES)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_target_user_id(self, value):
        from account.models import UserAccount
        if not UserAccount.objects.filter(pk=value).exists():
            raise serializers.ValidationError('Пользователь не найден.')
        return value

    def validate_permission_codes(self, value):
        from account.models_rbac import AppPermission
        existing = set(
            AppPermission.objects.filter(code__in=value, is_active=True)
            .values_list('code', flat=True)
        )
        missing = set(value) - existing
        if missing:
            raise serializers.ValidationError(
                f"Неизвестные права: {', '.join(missing)}"
            )
        return value

    def validate(self, attrs):
        request = self.context['request']
        user = request.user

        from account.models_rbac import ProfileAssignment
        from account.services.permissions import assignment_permission_codes, role_permission_codes

        role = getattr(user, 'role', None)
        dept_id = None
        try:
            emp = user.employee_info
            dept_id = emp.department_id if emp else None
        except Exception:
            pass

        from django.db.models import Q
        query = Q()
        if role:
            query |= Q(scope_type=ProfileAssignment.SCOPE_ROLE, role=role)
        if dept_id:
            query |= Q(scope_type=ProfileAssignment.SCOPE_DEPARTMENT, department_id=dept_id)

        can_delegate = query and ProfileAssignment.objects.filter(
            query, can_delegate=True
        ).exists()

        if not can_delegate and not user.is_superuser:
            raise serializers.ValidationError(
                'Вам не разрешена делегация прав.'
            )

        user_codes = (
            role_permission_codes(role) |
            assignment_permission_codes(user)
        )
        requested = set(attrs['permission_codes'])
        forbidden = requested - user_codes

        if forbidden and not user.is_superuser:
            raise serializers.ValidationError(
                f"Нельзя делегировать права, которых у вас нет: {', '.join(forbidden)}"
            )

        return attrs