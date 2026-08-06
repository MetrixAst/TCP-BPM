from django.urls import path

from account.role_permissions import login_required, need_permission, PermissionEnums
from . import views

_perm = need_permission(PermissionEnums.ECOPARK)
_cb = views.work_editor_callback  

urlpatterns = [
    path('',                           _perm(views.home),            name='home'),
    path('create',                     _perm(views.create),          name='create'),
    path('item/<int:pk>',              _perm(views.item),            name='item'),
    path('item/<int:pk>/edit',         _perm(views.edit),            name='edit'),
    path('item/<int:pk>/delete',       _perm(views.delete),          name='delete'),
    path('item/<int:pk>/editor/',      _perm(views.work_editor),     name='work_editor'),
    path('item/<int:pk>/editor/callback/', _cb,                      name='work_editor_callback'),
    path('item/<int:pk>/delete-doc/',  _perm(views.work_delete_doc), name='work_delete_doc'),
]