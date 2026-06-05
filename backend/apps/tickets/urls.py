from django.urls import path
from . import views

urlpatterns = [
    path('', views.tickets, name="home"),
    path('create/', views.create, name="create"),
    path('kanban/', views.kanban, name="kanban"),
    path('api/kanban/', views.kanban_api, name="kanban_api"),
    path('api/kanban/<int:pk>/status/', views.kanban_status, name="kanban_status"),
    path('item/<int:pk>/', views.item, name="item"),
    path('item/<int:pk>/action/', views.action, name="action"),
    path('item/<int:pk>/assign/', views.assign, name="assign"),
]
