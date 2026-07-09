from django.urls import path

from .views import DeviceView, MeView

app_name = 'mobile_api'

urlpatterns = [
    path('me/', MeView.as_view(), name='me'),
    path('devices/', DeviceView.as_view(), name='devices'),
]