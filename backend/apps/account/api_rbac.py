from django.db.models import Count, Q
from django_filters import rest_framework as filters
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from account.drf_permissions import HasAppPermission
from account.models import UserAccount
from account.models_rbac import AppPermission, PermissionProfile, UserPermissionOverride, ProfileAssignment
from account.role_permissions import PermissionEnums
from account.serializers_rbac import (
    AppPermissionSerializer,
    DelegationSerializer,
    PermissionProfileSerializer,
    ProfileAssignmentSerializer,
    UserListSerializer,
    UserMatrixSerializer,
    UserPermissionOverrideSerializer,
)



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
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = UserPermissionOverrideSerializer(
            override,
            data=request.data,
            partial=(request.method == 'PATCH'),
            context={'user': user, 'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
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