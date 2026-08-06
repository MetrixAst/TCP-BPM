from rest_framework import serializers

from account.models import UserAccount
from account.models_rbac import AppPermission, PermissionProfile, UserPermissionOverride


class AppPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppPermission
        fields = ['id', 'code', 'category', 'label', 'is_active']


class PermissionProfileSerializer(serializers.ModelSerializer):
    permissions = AppPermissionSerializer(many=True, read_only=True)

    class Meta:
        model = PermissionProfile
        fields = ['id', 'name', 'role', 'is_system', 'permissions']


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

    class Meta:
        model = UserAccount
        fields = ['id', 'username', 'full_name', 'role', 'overrides', 'role_permissions']

    def get_overrides(self, obj):
        qs = obj.permission_overrides.select_related('permission').all()
        return UserPermissionOverrideSerializer(qs, many=True, read_only=True).data

    def get_role_permissions(self, obj):
        try:
            profile = PermissionProfile.objects.get(role=obj.role)
            return list(profile.permissions.filter(is_active=True).values_list('code', flat=True))
        except PermissionProfile.DoesNotExist:
            return []


class UserListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_name', read_only=True)
    override_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = UserAccount
        fields = ['id', 'username', 'full_name', 'role', 'override_count']