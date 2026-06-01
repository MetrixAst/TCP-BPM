from django.urls import path
from . import views

app_name = 'settings'

urlpatterns = [
    path('counterparty-types/',
         views.counterparty_types, name='counterparty_types'),

    path('counterparty-types/create/',
         views.counterparty_type_create, name='counterparty_type_create'),

    path('counterparty-types/<int:pk>/edit/',
         views.counterparty_type_edit, name='counterparty_type_edit'),

    path('counterparty-types/<int:pk>/delete/',
         views.counterparty_type_delete, name='counterparty_type_delete'),

    path('counterparty-access/',
         views.counterparty_access, name='counterparty_access'),

    path('counterparty-access/create/',
         views.access_scope_create, name='access_scope_create'),

    path('counterparty-access/<int:pk>/delete/',
         views.access_scope_delete, name='access_scope_delete'),
]
