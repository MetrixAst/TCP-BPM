from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.tasks, name="list"),
    path('list/<str:action>', views.tasks_list, name="by_type"),

    path('task/<int:pk>', views.task, name="task"),
    path('task/<int:pk>/action/<str:action>', views.task_action, name="task_action"),
    path('task/<int:pk>/edit', views.edit_task, name="edit"),
    path('kanban/view/', views.kanban, name="kanban"),
    path('kanban/', views.kanban_board, name="kanban_board"),
    path('kanban/<int:pk>/status/', views.kanban_patch_status, name="kanban_patch_status"),
    path('task/<int:task_pk>/checklist/', views.checklist_create, name="checklist_create"),
    path('task/<int:task_pk>/checklist/<int:item_pk>/', views.checklist_update, name="checklist_update"),
    path('task/<int:task_pk>/checklist/<int:item_pk>/delete/', views.checklist_delete, name="checklist_delete"),
    path('task/<int:task_pk>/line-items/', views.line_items_list, name="line_items_list"),
    path('task/<int:task_pk>/line-items/create/', views.line_item_create, name="line_item_create"),
    path('task/<int:task_pk>/line-items/<int:item_pk>/delete/', views.line_item_delete, name="line_item_delete"),
]