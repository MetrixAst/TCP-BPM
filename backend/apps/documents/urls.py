from django.urls import path, include
from django.views.generic import RedirectView
from . import views
from . import views_acl
urlpatterns = [
    path('', RedirectView.as_view(url='/doc/documents/', permanent=False)),
    path('<slug:document_type>/', views.documents, name="list"),
    path('<slug:document_type>/folder/<int:folder>/', views.documents_folder_list, name="by_folder"),
    path('<slug:document_type>/status/<slug:status>/', views.documents_status_list, name="by_status"),
    path('<slug:document_type>/edit/<int:pk>/', views.edit_document, name="edit"),
    path('<slug:document_type>/folders/create/', views.create_folder_view, name="folder_create"),
    path('document/<int:pk>/', views.document_view, name="document"),
    path('document/<int:pk>/action/', views.document_action_view, name="document_action"),
    path('document/<int:pk>/esigner/send/', views.document_esigner_send, name="document_esigner_send"),
    path('document/<int:pk>/frame/', views.document_frame, name="document_frame"),
    path('document/<int:pk>/editor/', views.document_editor, name="document_editor"),
    path('document/<int:pk>/file/<slug:kind>/<int:file_pk>/delete/', views.document_file_delete, name="document_file_delete"),
    path('document/<int:pk>/onlyoffice/callback/', views.onlyoffice_callback, name="onlyoffice_callback"),
    path('document/upload_addit/<int:pk>/', views.upload_addit_document, name="upload_addit"),
    path('document/addit/<int:pk>/', views.addit_document_frame, name="addit_document_frame"),
    path('attachment/<slug:kind>/<int:pk>/editor/', views.attachment_editor, name="attachment_editor"),
    path(
        'attachment/<slug:kind>/<int:pk>/onlyoffice/callback/',
        views.onlyoffice_universal_callback,
        name="onlyoffice_universal_callback",
    ),
    path(
        '<slug:document_type>/settings/folders/',
        views_acl.folder_access_list,
        name='folder_access_list',
    ),
    path(
        '<slug:document_type>/settings/folders/<int:pk>/',
        views_acl.folder_access_edit,
        name='folder_access_edit',
    ),
]