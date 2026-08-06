from django.db.models import Count, Q
from django_filters import rest_framework as filters
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from account.drf_permissions import HasAppPermission
from account.models import UserAccount
from account.models_rbac import AppPermission, PermissionProfile, UserPermissionOverride
from account.role_permissions import PermissionEnums
from account.serializers_rbac import (
    AppPermissionSerializer,
    PermissionProfileSerializer,
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


class PermissionProfileViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsPermissionAdmin]
    queryset = PermissionProfile.objects.prefetch_related('permissions').order_by('name')
    serializer_class = PermissionProfileSerializer


class AppPermissionCatalogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsPermissionAdmin]
    queryset = AppPermission.objects.filter(is_active=True).order_by('category', 'code')
    serializer_class = AppPermissionSerializer
    filterset_fields = ['category']