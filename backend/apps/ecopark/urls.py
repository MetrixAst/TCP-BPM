from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name="home"),
    path('create', views.create, name="create"),
    path('item/<int:pk>', views.item, name="item"),
    path('item/<int:pk>/edit', views.edit, name="edit"),
    path('item/<int:pk>/delete', views.delete, name="delete"),
    path('item/<int:pk>/editor/', views.work_editor, name="work_editor"),
    path('item/<int:pk>/editor/callback/', views.work_editor_callback, name="work_editor_callback"),
    path('item/<int:pk>/delete-doc/', views.work_delete_doc, name="work_delete_doc"),
]