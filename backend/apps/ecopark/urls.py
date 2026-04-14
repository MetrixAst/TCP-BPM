from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name="home"),
    path('create', views.create, name="create"),
    path('item/<int:pk>', views.item, name="item"),
]