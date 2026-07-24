from django_filters import rest_framework as filters
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.exceptions import PermissionDenied

from account.drf_permissions import TasksPermission
from .models import Task
from .serializers import TaskSerializer


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
