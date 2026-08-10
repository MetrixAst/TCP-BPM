from django_filters import rest_framework as filters
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.exceptions import PermissionDenied

from account.drf_permissions import TasksPermission
from .models import Task
from .serializers import TaskSerializer
from mobile_api.idempotency import idempotent


class TaskFilter(filters.FilterSet):
    status = filters.CharFilter(field_name='status')
    priority = filters.CharFilter(field_name='priority')
    author = filters.NumberFilter(field_name='author_id')
    executor = filters.NumberFilter(field_name='executor_id')

    class Meta:
        model = Task
        fields = ['status', 'priority', 'author', 'executor']


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [TasksPermission]
    filterset_class = TaskFilter
    search_fields = ['title', 'text']
    ordering_fields = ['id', 'deadline', 'date', 'status', 'priority']
    ordering = ['-id']

    def get_queryset(self):
        return Task.get_available_queryset(self.request)

    def perform_create(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        task = self.get_object()
        if not task.can_delete(request.user):
            return Response(
                {'detail': 'Нет прав на удаление.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        reason = request.data.get('reason', '').strip()
        if len(reason) < 5:
            return Response(
                {'detail': 'Причина должна содержать не менее 5 символов.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        task.soft_delete(request.user, reason=reason)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='restore')
    def restore(self, request, pk=None):
        task = Task.objects.filter(pk=pk, deleted_at__isnull=False).first()
        if not task:
            return Response({'detail': 'Задача не найдена или не удалена.'}, status=status.HTTP_404_NOT_FOUND)
        if not task.can_delete(request.user):
            return Response({'detail': 'Нет прав на восстановление.'}, status=status.HTTP_403_FORBIDDEN)
        task.restore()
        return Response(TaskSerializer(task).data)

    @idempotent('task-transition')
    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        task = self.get_object()
        action_name = request.data.get('action')
        if not action_name:
            return Response(
                {'detail': 'Поле action обязательно.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            task.set_action(request, action_name)
        except PermissionDenied as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(task)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='bin')
    def bin(self, request):
        from account.role_permissions import RoleEnums
        role = getattr(request.user, 'role', None)
        if hasattr(role, 'value'):
            role = role.value
        if not (getattr(request.user, 'is_superuser', False) or role == RoleEnums.ADMINISTRATOR.value):
            return Response({'detail': 'Нет доступа.'}, status=status.HTTP_403_FORBIDDEN)

        qs = Task.objects.filter(deleted_at__isnull=False).order_by('-deleted_at')
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(TaskSerializer(page, many=True).data)
        return Response(TaskSerializer(qs, many=True).data)
    
