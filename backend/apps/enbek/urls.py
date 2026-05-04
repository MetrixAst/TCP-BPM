from django.urls import path
from . import views

urlpatterns = [
    path('auth/login/', views.login),
    path('contracts/', views.contracts),
    path('leaves/', views.leaves),
    path('sick-leaves/', views.sick_leaves),
]