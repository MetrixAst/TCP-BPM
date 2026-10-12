from django.urls import path, include
from . import views
urlpatterns = [
    path('', views.home, name="list"),
    path('create/', views.create_tenant, name="create"),
    path('import/', views.import_tenants_view, name="import"),
    path('<int:pk>/portal-access/', views.tenant_portal_access, name="portal_access"),
    path('<int:pk>/', views.tenant_detail, name="detail"),
    path('<int:pk>/edit/', views.edit_tenant, name="edit"),
    path('<int:pk>/delete/', views.delete_tenant, name="delete"),
    path('<int:pk>/archive/', views.toggle_tenant_archive, name="archive"),
    path('all_json', views.all_json, name="all_json"),
    path('rooms/<int:pk>/qr-label/', views.room_qr_label, name="room_qr_label"),
    path('rooms/qr-labels/', views.rooms_qr_labels_batch, name="rooms_qr_labels_batch"),
]