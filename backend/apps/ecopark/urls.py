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

    path('inspection/points/', _perm(views.inspection_points), name='inspection_points'),
    path('inspection/points/create/', _perm(views.inspection_point_create), name='inspection_point_create'),
    path('inspection/points/<int:pk>/edit/', _perm(views.inspection_point_edit), name='inspection_point_edit'),
    path('inspection/points/<int:pk>/delete/', _perm(views.inspection_point_delete), name='inspection_point_delete'),
    path('inspection/points/<int:pk>/qr/', _perm(views.inspection_point_qr), name='inspection_point_qr'),

    path('inspection/scan/<str:qr_code>/', views.inspection_scan, name='inspection_scan'),
    path('inspection/round/<int:pk>/', _perm(views.inspection_round_detail), name='inspection_round_detail'),
    path('inspection/journal/', _perm(views.inspection_journal), name='inspection_journal'),
    path('inspection/report/', _perm(views.inspection_report), name='inspection_report'),
    path('inspection/export/', _perm(views.inspection_export), name='inspection_export'),

    path('inspection/api/submit/', views.inspection_submit, name='inspection_submit'),
    path('inspection/api/defect/<int:pk>/escalate/', _perm(views.defect_escalate), name='defect_escalate'),
]