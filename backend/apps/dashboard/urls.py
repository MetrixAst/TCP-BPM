from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.base_redirect, name="base"),
    path('dashboard', views.dashboard, name="dashboard"),
]