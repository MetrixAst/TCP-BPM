from django.urls import path
from . import views

urlpatterns = [
    path("webhook/", views.esigner_webhook, name="webhook"),
]