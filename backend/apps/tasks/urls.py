from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.tasks, name="list"),
    path('list/<str:action>', views.tasks_list, name="by_type"),
    path('kanban/', views.kanban, name="kanban"),
    path('api/kanban/', views.kanban_api, name="kanban_api"),
    path('api/kanban/<int:pk>/status/', views.kanban_status, name="kanban_status"),

    path('task/<int:pk>', views.task, name="task"),
    path('task/<int:pk>/action/<str:action>', views.task_action, name="task_action"),
    path('task/<int:pk>/edit', views.edit_task, name="edit"),
    path('task/<int:pk>/checklist/', views.checklist_add, name="checklist_add"),
    path('task/<int:pk>/checklist/<int:item_id>/toggle/', views.checklist_toggle, name="checklist_toggle"),
    path('task/<int:pk>/line-items/', views.line_item_add, name="line_item_add"),
    path('task/<int:pk>/files/', views.task_file_add, name="file_add"),
    path('task/<int:pk>/files/<int:file_id>/delete/', views.task_file_delete, name="file_delete"),
    path('task/<int:pk>/counterparty/', views.task_counterparty, name="task_counterparty"),
    path('task/<int:pk>/flag/', views.task_toggle_flag, name="task_flag"),
]