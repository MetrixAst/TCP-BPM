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
    path('item/<int:pk>/messages/', views.messages_list, name="messages_list"),
    path('item/<int:pk>/messages/send/', views.message_send, name="message_send"),
    path('item/<int:pk>/attachments/', views.attachments_list, name="attachments_list"),
    path('item/<int:pk>/attachments/upload/', views.attachment_upload, name="attachment_upload"),
    path('item/<int:pk>/attachments/<int:attachment_pk>/delete/', views.attachment_delete, name="attachment_delete"),
    path('approvals/', views.approval_queue, name="approvals"),
    path('workflow/', views.workflow_settings, name="workflow_settings"),
    path('workflow/new/', views.workflow_settings_edit, name="workflow_settings_create"),
    path('workflow/<int:pk>/edit/', views.workflow_settings_edit, name="workflow_settings_edit"),
    path('workflow/<int:pk>/delete/', views.workflow_settings_delete, name="workflow_settings_delete")
]
