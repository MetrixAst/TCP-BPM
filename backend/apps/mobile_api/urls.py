from django.urls import path

from .views import (
    DeviceView, MeView,
    AttendanceCheckinView, AttendanceTodayView,
    TicketListCreateView, TicketDetailView,
    TicketMessagesView,
    NotificationsListView, NotificationReadView,
    RoomResolveView,
    AttendanceQRCheckinView,
    AttendanceOfficeQRCheckinView,
    RoundsTodayView,
    RoundsResolveQRView,
    RoundDetailView,
    RoundPointDetailView,
    RoundPointAnswerView,
)


app_name = 'mobile_api'

urlpatterns = [
    path('me/', MeView.as_view(), name='me'),
    path('devices/', DeviceView.as_view(), name='devices'),
    path('attendance/checkin/', AttendanceCheckinView.as_view(), name='attendance-checkin'),
    path('attendance/today/', AttendanceTodayView.as_view(), name='attendance-today'),
    path('tickets/', TicketListCreateView.as_view(), name='tickets-list-create'),
    path('tickets/<int:pk>/', TicketDetailView.as_view(), name='tickets-detail'),
    path('tickets/<int:pk>/messages/', TicketMessagesView.as_view(), name='tickets-messages'),
    path('notifications/', NotificationsListView.as_view(), name='notifications-list'),
    path('notifications/<int:pk>/read/', NotificationReadView.as_view(), name='notifications-read'),
    path('rooms/resolve/', RoomResolveView.as_view(), name='room-resolve'),
    path('attendance/qr-checkin/', AttendanceQRCheckinView.as_view(), name='attendance-qr-checkin'),
    path('attendance/office-qr/<uuid:public_id>/checkin/', AttendanceOfficeQRCheckinView.as_view(), name='attendance-office-qr-checkin'),
    path('rounds/today/', RoundsTodayView.as_view(), name='rounds-today'),
    path('rounds/resolve/', RoundsResolveQRView.as_view(), name='rounds-resolve'),
    path('rounds/points/<uuid:point_uuid>/', RoundPointDetailView.as_view(), name='round-point-detail'),
    path('rounds/<int:pk>/', RoundDetailView.as_view(), name='round-detail'),
    path('rounds/<int:pk>/points/<uuid:point_uuid>/answer/', RoundPointAnswerView.as_view(), name='round-point-answer'),
]