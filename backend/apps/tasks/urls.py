from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.tasks, name="list"),
    path('list/<str:action>', views.tasks_list, name="by_type"),

    path('task/<int:pk>', views.task, name="task"),
    path('task/<int:pk>/action/<str:action>', views.task_action, name="task_action"),
    path('task/<int:pk>/edit', views.edit_task, name="edit"),
]