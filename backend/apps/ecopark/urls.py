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

    # Обходы: точки
    path('rounds/points/',               _perm(views.round_points_list), name='round_points_list'),
    path('rounds/points/create/',        _perm(views.round_point_create), name='round_point_create'),
    path('rounds/points/<int:pk>/edit/', _perm(views.round_point_edit),   name='round_point_edit'),
    path('rounds/points/<int:pk>/delete/', _perm(views.round_point_delete), name='round_point_delete'),
    path('rounds/points/<int:pk>/label/',  _perm(views.round_point_label),  name='round_point_label'),

    # Обходы: чек-листы
    path('rounds/checklists/',               _perm(views.checklist_templates_list),  name='checklist_templates_list'),
    path('rounds/checklists/create/',        _perm(views.checklist_template_create), name='checklist_template_create'),
    path('rounds/checklists/<int:pk>/edit/', _perm(views.checklist_template_edit),   name='checklist_template_edit'),
    path('rounds/checklists/<int:pk>/delete/', _perm(views.checklist_template_delete), name='checklist_template_delete'),

    # Прохождение обхода — только login_required, без ECOPARK (любой сотрудник)
    path('rounds/scan/<uuid:point_uuid>/', views.rounds_scan, name='rounds_scan'),

    # Журнал/KPI и неисправности — доступ через _rounds_monitor_required внутри view
    path('rounds/journal/',                views.rounds_journal,  name='rounds_journal'),
    path('rounds/defects/',                views.defects_list,    name='defects_list'),
    path('rounds/defects/<int:pk>/resolve/', views.defect_resolve, name='defect_resolve'),
]