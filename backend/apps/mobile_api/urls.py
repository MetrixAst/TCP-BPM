from django.urls import path

from .views import (
    DeviceView, MeView,
    AttendanceCheckinView, AttendanceTodayView,
    TicketListCreateView, TicketDetailView,
)

app_name = 'mobile_api'

urlpatterns = [
    path('me/', MeView.as_view(), name='me'),
    path('devices/', DeviceView.as_view(), name='devices'),
    path('attendance/checkin/', AttendanceCheckinView.as_view(), name='attendance-checkin'),
    path('attendance/today/', AttendanceTodayView.as_view(), name='attendance-today'),
    path('tickets/', TicketListCreateView.as_view(), name='tickets-list-create'),
    path('tickets/<int:pk>/', TicketDetailView.as_view(), name='tickets-detail'),
]