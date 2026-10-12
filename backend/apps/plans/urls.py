from django.urls import path

from . import views

urlpatterns = [
    path('', views.plans_list, name='list'),
    path('export/', views.plans_export, name='export'),
    path('create/', views.plan_create, name='create'),
    path('<int:pk>/', views.plan_detail, name='detail'),
    path('<int:pk>/note/', views.plan_update_note, name='note'),
    path('<int:pk>/delete/', views.plan_delete, name='delete'),
    path('<int:pk>/items/add/', views.item_create, name='item_create'),
    path('items/<int:pk>/edit/', views.item_edit, name='item_edit'),
    path('items/<int:pk>/status/', views.item_status, name='item_status'),
    path('items/<int:pk>/delete/', views.item_delete, name='item_delete'),
    path('items/<int:pk>/task/', views.item_create_task, name='item_create_task'),
]
