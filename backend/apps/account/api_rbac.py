from django.db.models import Count, Q
from django_filters import rest_framework as filters
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers

from account.drf_permissions import HasAppPermission
from account.models import UserAccount, Notification, NotificationUser
from account.models_rbac import AppPermission, PermissionProfile, UserPermissionOverride, ProfileAssignment, TemporaryAccess
from account.role_permissions import PermissionEnums
from account.serializers_rbac import (
    AppPermissionSerializer,
    DelegationSerializer,
    PermissionProfileSerializer,
    ProfileAssignmentSerializer,
    UserListSerializer,
    UserMatrixSerializer,
    UserPermissionOverrideSerializer,
    PermissionAuditLogSerializer,
    TemporaryAccessSerializer
)
from django.utils import timezone
from django.shortcuts import get_object_or_404


class IsPermissionAdmin(HasAppPermission):
    permission = PermissionEnums.MANAGE_PERMISSIONS


class UserFilter(filters.FilterSet):
    role = filters.CharFilter(field_name='role')
    username = filters.CharFilter(field_name='username', lookup_expr='icontains')
    full_name = filters.CharFilter(method='filter_full_name')
    has_overrides = filters.BooleanFilter(method='filter_has_overrides')
    department = filters.NumberFilter(field_name='employee_info__department_id')
    employee_status = filters.CharFilter(field_name='employee_info__status')

    class Meta:
        model = UserAccount
        fields = ['role', 'username', 'department', 'employee_status']

    def filter_full_name(self, qs, name, value):
        return qs.filter(
            Q(first_name__icontains=value) | Q(last_name__icontains=value)
        )

    def filter_has_overrides(self, qs, name, value):
        if value:
            return qs.filter(override_count__gt=0)
        return qs.filter(override_count=0)


class UserPermissionsViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsPermissionAdmin]
    serializer_class = UserMatrixSerializer
    filterset_class = UserFilter
    search_fields = ['username', 'first_name', 'last_name']
    ordering_fields = ['username', 'role', 'override_count']
    ordering = ['username']

    def get_queryset(self):
        return (
            UserAccount.objects
            .select_related('employee_info__department')
            .annotate(override_count=Count('permission_overrides'))
            .order_by('username')
        )

    def get_user_or_404(self, pk):
        try:
            return UserAccount.objects.select_related('employee_info__department').get(pk=pk)
        except UserAccount.DoesNotExist:
            raise NotFound(f"Пользователь {pk} не найден.")

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(UserListSerializer(page, many=True).data)
        return Response(UserListSerializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        user = self.get_user_or_404(pk)
        return Response(UserMatrixSerializer(user).data)

    @action(detail=True, methods=['get', 'post'], url_path='overrides')
    def overrides(self, request, pk=None):
        user = self.get_user_or_404(pk)
        if request.method == 'GET':
            qs = user.permission_overrides.select_related('permission').all()
            return Response(UserPermissionOverrideSerializer(qs, many=True).data)

        serializer = UserPermissionOverrideSerializer(
            data=request.data,
            context={'user': user, 'request': request},
        )
        serializer.is_valid(raise_exception=True)
        override = serializer.save()

        from account.models_rbac import PermissionAuditLog
        ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
        PermissionAuditLog.objects.filter(
            target_user=user,
            permission_code=override.permission.code,
        ).order_by('-created_at').first().__class__.objects.filter(
            target_user=user,
            permission_code=override.permission.code,
        ).order_by('-created_at').update(ip_address=ip)

        return Response(
            UserPermissionOverrideSerializer(override).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['put', 'patch', 'delete'], url_path=r'overrides/(?P<oid>\d+)')
    def override_detail(self, request, pk=None, oid=None):
        user = self.get_user_or_404(pk)
        try:
            override = UserPermissionOverride.objects.get(pk=oid, user=user)
        except UserPermissionOverride.DoesNotExist:
            raise NotFound("Переопределение не найдено.")

        if request.method == 'DELETE':
            override.delete()
            from account.models_rbac import PermissionAuditLog
            ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
            PermissionAuditLog.objects.filter(
                target_user=user,
                permission_code=override.permission.code,
                action=PermissionAuditLog.ACTION_OVERRIDE_DELETE,
            ).order_by('-created_at').update(ip_address=ip)
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = UserPermissionOverrideSerializer(
            override,
            data=request.data,
            partial=(request.method == 'PATCH'),
            context={'user': user, 'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        from account.models_rbac import PermissionAuditLog
        ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
        PermissionAuditLog.objects.filter(
            target_user=user,
            permission_code=override.permission.code,
            action=PermissionAuditLog.ACTION_OVERRIDE_CHANGE,
        ).order_by('-created_at').update(ip_address=ip)

        return Response(serializer.data)

class PermissionProfileViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsPermissionAdmin]
    queryset = PermissionProfile.objects.prefetch_related('permissions').order_by('name')
    serializer_class = PermissionProfileSerializer

    def destroy(self, request, *args, **kwargs):
        profile = self.get_object()
        if profile.is_system:
            return Response(
                {'error': 'Системный профиль нельзя удалить.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['patch'], url_path='set-permissions')
    def set_permissions(self, request, pk=None):
        profile = self.get_object()
        ids = request.data.get('permission_ids', [])
        if not isinstance(ids, list):
            return Response(
                {'error': 'permission_ids должен быть списком'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        perms = AppPermission.objects.filter(id__in=ids, is_active=True)
        profile.permissions.set(perms)
        return Response(PermissionProfileSerializer(profile).data)


class AppPermissionCatalogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsPermissionAdmin]
    queryset = AppPermission.objects.filter(is_active=True).order_by('category', 'code')
    serializer_class = AppPermissionSerializer
    filterset_fields = ['category']

class ProfileAssignmentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPermissionAdmin]
    serializer_class = ProfileAssignmentSerializer
    queryset = ProfileAssignment.objects.select_related(
        'profile', 'department', 'assigned_by'
    ).order_by('scope_type', 'role', 'department_id')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    @action(detail=True, methods=['get'], url_path='preview')
    def preview(self, request, pk=None):
        assignment = self.get_object()
        from account.models import UserAccount

        if assignment.scope_type == ProfileAssignment.SCOPE_ROLE:
            users = UserAccount.objects.filter(
                role=assignment.role
            ).select_related('employee_info__department')
        else:
            users = UserAccount.objects.filter(
                employee_info__department_id=assignment.department_id
            ).select_related('employee_info__department')

        data = UserListSerializer(
            users.annotate(
                override_count=Count('permission_overrides')
            ),
            many=True,
        ).data
        return Response({
            'assignment': ProfileAssignmentSerializer(assignment).data,
            'affected_users_count': len(data),
            'affected_users': data,
        })


class DelegationViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='')
    def delegate(self, request):
        serializer = DelegationSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)

        target_user_id = serializer.validated_data['target_user_id']
        permission_codes = serializer.validated_data['permission_codes']
        effect = serializer.validated_data['effect']
        reason = serializer.validated_data.get('reason', '')

        from account.models import UserAccount
        target_user = UserAccount.objects.get(pk=target_user_id)

        created = []
        skipped = []

        for code in permission_codes:
            perm = AppPermission.objects.get(code=code)
            override, was_created = UserPermissionOverride.objects.get_or_create(
                user=target_user,
                permission=perm,
                defaults={
                    'effect': effect,
                    'reason': reason or f'Делегировано пользователем {request.user.username}',
                    'created_by': request.user,
                }
            )
            if was_created:
                created.append(code)
            else:
                skipped.append(code)

        return Response({
            'target_user_id': target_user_id,
            'created': created,
            'skipped_existing': skipped,
            'message': (
                f'Делегировано: {len(created)} прав. '
                f'Пропущено (уже есть переопределение): {len(skipped)}.'
            ),
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

class PermissionAuditLogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsPermissionAdmin]
    serializer_class = PermissionAuditLogSerializer

    def get_queryset(self):
        from account.models_rbac import PermissionAuditLog
        qs = PermissionAuditLog.objects.select_related(
            'actor', 'target_user', 'profile'
        ).order_by('-created_at')

        action = self.request.query_params.get('action')
        if action:
            qs = qs.filter(action=action)

        user_id = self.request.query_params.get('user_id')
        if user_id:
            qs = qs.filter(target_user_id=user_id)

        permission_code = self.request.query_params.get('permission_code')
        if permission_code:
            qs = qs.filter(permission_code=permission_code)

        return qs


class NotificationSerializer(drf_serializers.Serializer):
    id = drf_serializers.IntegerField()
    title = drf_serializers.CharField()
    text = drf_serializers.CharField()
    created_date = drf_serializers.DateTimeField()
    target_id = drf_serializers.IntegerField()
    target_type = drf_serializers.CharField()
    is_read = drf_serializers.BooleanField()
    url = drf_serializers.CharField(allow_null=True)

class NotificationViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(users=self.request.user).order_by('-created_date')

    def list(self, request):
        qs = self.get_queryset()
        data = [{
            'id': n.pk,
            'title': n.title,
            'text': n.text,
            'created_date': n.created_date.isoformat(),
            'target_id': n.target_id,
            'target_type': n.target_type,
            'url': n.url,
            'is_read': NotificationUser.objects.filter(
                notification=n, user=request.user
            ).values_list('is_read', flat=True).first() or False,
        } for n in qs]
        return Response(data)

    @action(detail=True, methods=['delete'], url_path='dismiss')
    def dismiss(self, request, pk=None):
        notification = get_object_or_404(
            Notification.objects.filter(users=request.user), pk=pk
        )
        notification.users.remove(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['delete'], url_path='dismiss-read')
    def dismiss_read(self, request):
        read_ids = NotificationUser.objects.filter(
            user=request.user, is_read=True
        ).values_list('notification_id', flat=True)
        Notification.objects.filter(pk__in=read_ids).first()
        for n in Notification.objects.filter(pk__in=read_ids):
            n.users.remove(request.user)
        return Response({'deleted': len(read_ids)})

    @action(detail=False, methods=['delete'], url_path='dismiss-all')
    def dismiss_all(self, request):
        qs = self.get_queryset()
        count = qs.count()
        for n in qs:
            n.users.remove(request.user)
        return Response({'deleted': count})

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = get_object_or_404(
            Notification.objects.filter(users=request.user), pk=pk
        )
        NotificationUser.objects.update_or_create(
            notification=notification,
            user=request.user,
            defaults={'is_read': True, 'read_at': timezone.now()},
        )
        return Response({'ok': True})

class TemporaryAccessViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPermissionAdmin]
    serializer_class = TemporaryAccessSerializer

    def get_queryset(self):
        from django.utils import timezone
        qs = TemporaryAccess.objects.select_related(
            'user', 'permission', 'granted_by', 'revoked_by'
        ).order_by('-created_at')

        status = self.request.query_params.get('status')
        user_id = self.request.query_params.get('user_id')
        active_only = self.request.query_params.get('active_only')

        if status:
            qs = qs.filter(status=status)
        if user_id:
            qs = qs.filter(user_id=user_id)
        if active_only == 'true':
            now = timezone.now()
            qs = qs.filter(
                status=TemporaryAccess.STATUS_ACTIVE,
                date_from__lte=now,
                date_to__gte=now,
            )
        return qs

    def _get_ip(self, request):
        return request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')

    def perform_create(self, serializer):
        from account.models_rbac import PermissionAuditLog
        instance = serializer.save(
            granted_by=self.request.user,
            ip_address=self._get_ip(self.request),
        )
        PermissionAuditLog.objects.create(
            action='GRANT',
            actor=self.request.user,
            target_user=instance.user,
            permission_code=instance.permission.code,
            ip_address=self._get_ip(self.request),
            after={'type': 'temporary', 'date_to': instance.date_to.isoformat()},
        )

    @action(detail=True, methods=['post'], url_path='revoke')
    def revoke(self, request, pk=None):
        from django.utils import timezone
        from account.models_rbac import PermissionAuditLog
        instance = self.get_object()
        if instance.status != TemporaryAccess.STATUS_ACTIVE:
            return Response({'error': 'Доступ уже неактивен.'}, status=400)
        instance.status = TemporaryAccess.STATUS_REVOKED
        instance.revoked_by = request.user
        instance.revoked_at = timezone.now()
        instance.save(update_fields=['status', 'revoked_by', 'revoked_at'])
        PermissionAuditLog.objects.create(
            action='REVOKE',
            actor=request.user,
            target_user=instance.user,
            permission_code=instance.permission.code,
            ip_address=self._get_ip(request),
        )
        return Response(TemporaryAccessSerializer(instance).data)

    @action(detail=True, methods=['patch'], url_path='extend')
    def extend(self, request, pk=None):
        from account.models_rbac import PermissionAuditLog
        instance = self.get_object()
        new_date_to = request.data.get('date_to')
        if not new_date_to:
            return Response({'error': 'Укажите дату окончания доступа.'}, status=400, json_dumps_params={'ensure_ascii': False})
        from django.utils import timezone
        from datetime import datetime
        try:
            new_date_to = datetime.fromisoformat(new_date_to)
            if new_date_to <= timezone.now():
                return Response({'error': 'Дата окончания должна быть в будущем.'}, status=400)
        except ValueError:
            return Response({'error': 'Неверный формат даты.'}, status=400)
        old_date_to = instance.date_to
        instance.date_to = new_date_to
        instance.save(update_fields=['date_to'])
        PermissionAuditLog.objects.create(
            action='GRANT',
            actor=request.user,
            target_user=instance.user,
            permission_code=instance.permission.code,
            ip_address=self._get_ip(request),
            before={'date_to': old_date_to.isoformat()},
            after={'date_to': new_date_to.isoformat()},
        )
        return Response(TemporaryAccessSerializer(instance).data)