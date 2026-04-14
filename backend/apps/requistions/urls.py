from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.items, name="home"),
    path('create/', views.create_init, name="create"),
    path('create/<int:pk>/', views.create_info, name="create_info"),

    path('item/<int:pk>/', views.item, name="item"),
    path('item/<int:pk>/action/', views.requistion_action, name="action"),
    path('item/<int:pk>/print/', views.item_print, name="print"),

    path('edit/<int:pk>/', views.edit, name="edit"),
]