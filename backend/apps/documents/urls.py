from django.urls import path, include
from . import views

urlpatterns = [
    path('<slug:document_type>/', views.documents, name="list"),
    path('<slug:document_type>/folder/<int:folder>/', views.documents_folder_list, name="by_folder"),
    path('<slug:document_type>/status/<slug:status>/', views.documents_status_list, name="by_status"),
    path('<slug:document_type>/edit/<int:pk>/', views.edit_document, name="edit"),


    path('document/<int:pk>/', views.document_view, name="document"),
    path('document/<int:pk>/action/', views.document_action_view, name="document_action"),
    path('document/<int:pk>/frame/', views.document_frame, name="document_frame"),


    path('document/upload_addit/<int:pk>/', views.upload_addit_document, name="upload_addit"),
    path('document/addit/<int:pk>/', views.addit_document_frame, name="addit_document_frame"),
]