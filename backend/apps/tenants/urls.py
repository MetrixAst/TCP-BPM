from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name="list"),
    path('create/', views.create_tenant, name="create"),
    path('all_json', views.all_json, name="all_json"),
]