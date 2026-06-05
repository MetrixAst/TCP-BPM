from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name="list"),
    path('create/', views.create_tenant, name="create"),
    path('<int:pk>/portal-access/', views.tenant_portal_access, name="portal_access"),
    path('all_json', views.all_json, name="all_json"),
]