from datetime import date

from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.pagination import PageNumberPagination

from django.core.exceptions import ValidationError as DjangoValidationError

from account.models import NotificationIndicator, PushToken, Notification
from account.role_permissions import MenuItem

from hr.models import AttendanceRecord
from hr.services import create_attendance_checkin

from tickets.models import ServiceRequest, TicketMessage
from .idempotency import idempotent
from tenants.models import Room

from .serializers import (
    ProfileSerializer,
    PushTokenSerializer,
    AttendanceCheckinSerializer,
    AttendanceRecordOutSerializer,
    ServiceRequestListSerializer,
    ServiceRequestDetailSerializer,
    ServiceRequestCreateSerializer,
    TicketMessageSerializer,
    TicketMessageCreateSerializer,
    NotificationSerializer,
    RoomResolveSerializer,
)


def _serialize_menu_item(item):
    return {
        'id': item.id,
        'title': item.title,
        'icon': item.icon,
        'url': item.url,
        'always_expanded': item.always_expanded,
        'indicator_alias': item.indicator_alias,
        'submenu': [_serialize_menu_item(sub) for sub in item.submenu] if item.submenu else [],
    }


class MeView(APIView):
    """GET /api/v1/mobile/me/ — профиль, меню, бейджи."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: OpenApiResponse(description='Профиль, меню и бейджи текущего пользователя')},
    )
    def get(self, request):
        user = request.user
        menu = MenuItem.generate_menu(user)
        badges = NotificationIndicator.get_data(user)
        first_page = MenuItem.first_page_as_string(user)

        return Response({
            'profile': ProfileSerializer(user).data,
            'menu': [_serialize_menu_item(item) for item in menu],
            'badges': badges,
            'first_page': first_page,
        })


class DeviceView(APIView):
    """Регистрация и отвязка FCM-токена устройства."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=PushTokenSerializer,
        responses={201: OpenApiResponse(description='Токен зарегистрирован (идемпотентно)')},
    )
    def post(self, request):
        serializer = PushTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fcm = serializer.validated_data['fcm']

        token, created = PushToken.objects.get_or_create(
            user=request.user,
            fcm=fcm,
        )
        return Response(
            {'id': token.id, 'created': created},
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=PushTokenSerializer,
        responses={200: OpenApiResponse(description='Устройство(а) отвязаны')},
        description='Без тела запроса удаляет все токены пользователя (logout). '
                     'С полем fcm — удаляет конкретный токен.',
    )
    def delete(self, request):
        fcm = request.data.get('fcm')
        qs = PushToken.objects.filter(user=request.user)
        if fcm:
            qs = qs.filter(fcm=fcm)
        deleted_count, _ = qs.delete()
        return Response({'deleted': deleted_count}, status=status.HTTP_200_OK)


class AttendanceCheckinView(APIView):
    """POST /api/v1/mobile/attendance/checkin/ — чек-ин с фото (multipart) + гео, JWT."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]

    @idempotent('attendance-checkin')

    @extend_schema(
        request=AttendanceCheckinSerializer,
        responses={201: OpenApiResponse(description='Отметка сохранена')},
    )
    def post(self, request):
        employee = getattr(request.user, 'employee_info', None)
        if not employee:
            return Response(
                {'error': 'Профиль сотрудника не найден'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AttendanceCheckinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            record = create_attendance_checkin(
                employee=employee,
                event_type=data['event_type'],
                photo_file=data['photo'],
                latitude=data.get('latitude'),
                longitude=data.get('longitude'),
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except DjangoValidationError as e:
            return Response({'error': e.messages[0]}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            AttendanceRecordOutSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )


class AttendanceTodayView(APIView):
    """GET /api/v1/mobile/attendance/today/ — статус отметок за сегодня, включая фото."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: OpenApiResponse(description='Список отметок за сегодня с фото')},
    )
    def get(self, request):
        employee = getattr(request.user, 'employee_info', None)
        if not employee:
            return Response(
                {'error': 'Профиль сотрудника не найден'},
                status=status.HTTP_403_FORBIDDEN,
            )

        records = AttendanceRecord.objects.filter(
            employee=employee,
            timestamp__date=date.today(),
        ).order_by('timestamp')

        marks = []
        for record in records:
            photo_url = None
            if record.photo:
                photo_url = request.build_absolute_uri(record.photo.url)
            marks.append({
                'type': record.event_type,
                'time': record.timestamp.isoformat(),
                'photo': photo_url,
                'location_address': record.location_address,
            })

        return Response({'marks': marks})


class TicketPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class TicketListCreateView(APIView):
    """
    GET  /api/v1/mobile/tickets/ — список + фильтры (status/category), пагинация.
    POST /api/v1/mobile/tickets/ — создание с фото (multipart).
    """

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        parameters=[
            OpenApiParameter('status', str, required=False),
            OpenApiParameter('category', str, required=False),
        ],
        responses={200: OpenApiResponse(description='Список заявок с пагинацией')},
    )
    def get(self, request):
        qs = ServiceRequest.get_available_queryset(request)

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        category_filter = request.query_params.get('category')
        if category_filter:
            qs = qs.filter(category=category_filter)

        paginator = TicketPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ServiceRequestListSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=ServiceRequestCreateSerializer,
        responses={201: OpenApiResponse(description='Заявка создана')},
    )
    def post(self, request):
        serializer = ServiceRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        ticket = ServiceRequest.objects.create(
            author=request.user,
            tenant=getattr(request.user, 'tenant', None),
            title=data['title'],
            description=data['description'],
            category=data['category'],
            priority=data.get('priority', ServiceRequest.PRIORITIES[1][0]),
            room=data.get('room', ''),
            photo=data.get('photo'),
        )

        from tickets.models import ServiceRequestHistory
        ServiceRequestHistory.objects.create(
            request=ticket,
            user=request.user,
            status=ticket.status,
            comment='Заявка создана',
        )

        return Response(
            ServiceRequestDetailSerializer(ticket, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class TicketDetailView(APIView):
    """GET /api/v1/mobile/tickets/{id}/ — детали заявки."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: OpenApiResponse(description='Детали заявки')},
    )
    def get(self, request, pk):
        ticket = ServiceRequest.get_available_queryset(request).filter(pk=pk).first()
        if ticket is None:
            return Response({'error': 'Заявка не найдена'}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            ServiceRequestDetailSerializer(ticket, context={'request': request}).data
        )

class TicketMessagesView(APIView):
    """
    GET  /api/v1/mobile/tickets/{id}/messages/ — сообщения чата заявки.
    POST /api/v1/mobile/tickets/{id}/messages/ — отправка сообщения.
    """

    permission_classes = [permissions.IsAuthenticated]

    def _get_ticket_or_404(self, request, pk):
        ticket = ServiceRequest.objects.filter(pk=pk).first()
        if ticket is None:
            return None
        if not TicketMessage.can_view(ticket, request.user):
            return None
        return ticket

    @extend_schema(
        responses={200: OpenApiResponse(description='Сообщения чата заявки')},
    )
    def get(self, request, pk):
        ticket = self._get_ticket_or_404(request, pk)
        if ticket is None:
            return Response({'error': 'Заявка не найдена'}, status=status.HTTP_404_NOT_FOUND)

        messages = ticket.messages.select_related('author').order_by('id')

        paginator = TicketPagination()
        page = paginator.paginate_queryset(messages, request)
        serializer = TicketMessageSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    @idempotent('ticket-message-create')
    @extend_schema(
        request=TicketMessageCreateSerializer,
        responses={201: OpenApiResponse(description='Сообщение отправлено')},
    )
    def post(self, request, pk):
        ticket = self._get_ticket_or_404(request, pk)
        if ticket is None:
            return Response({'error': 'Заявка не найдена'}, status=status.HTTP_404_NOT_FOUND)

        serializer = TicketMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = TicketMessage.objects.create(
            request=ticket,
            author=request.user,
            text=serializer.validated_data['text'],
        )

        return Response(
            TicketMessageSerializer(message).data,
            status=status.HTTP_201_CREATED,
        )

class NotificationsListView(APIView):
    """GET /api/v1/mobile/notifications/ — лента уведомлений с флагом прочтения."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: OpenApiResponse(description='Лента уведомлений пользователя')},
    )
    def get(self, request):
        notifications = Notification.objects.filter(users=request.user).order_by('-id')

        unread = NotificationIndicator.objects.filter(user=request.user).values_list(
            'target_type', 'target_id'
        )
        unread_targets = set(unread)

        paginator = TicketPagination()
        page = paginator.paginate_queryset(notifications, request)
        serializer = NotificationSerializer(
            page, many=True, context={'unread_targets': unread_targets}
        )
        return paginator.get_paginated_response(serializer.data)


class NotificationReadView(APIView):
    """POST /api/v1/mobile/notifications/{id}/read/ — отметить прочитанным."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: OpenApiResponse(description='Уведомление отмечено прочитанным')},
    )
    def post(self, request, pk):
        notification = Notification.objects.filter(pk=pk, users=request.user).first()
        if notification is None:
            return Response({'error': 'Уведомление не найдено'}, status=status.HTTP_404_NOT_FOUND)

        NotificationIndicator.readed(request.user, notification.target_id, notification.target_type)

        return Response({'success': True})

class RoomResolveView(APIView):
    """
    GET /api/v1/mobile/rooms/resolve/?map_id=<value>

    Резолвит map_id из QR-кода помещения в данные комнаты для
    предзаполнения формы создания заявки. Защищён тем же JWT, что и
    весь mobile_api — сам map_id в QR передаётся как обычный текст,
    авторизация нужна на уровне запроса к API, не на уровне QR-кода.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[OpenApiParameter('map_id', str, required=True)],
        responses={200: OpenApiResponse(description='Данные помещения')},
    )
    def get(self, request):
        map_id = request.query_params.get('map_id')
        if not map_id:
            return Response({'error': 'Параметр map_id обязателен'}, status=status.HTTP_400_BAD_REQUEST)

        room = Room.objects.filter(map_id=map_id).first()
        if room is None:
            return Response({'error': 'Помещение не найдено'}, status=status.HTTP_404_NOT_FOUND)

        return Response(RoomResolveSerializer(room).data)


class AttendanceQRCheckinView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @idempotent('attendance-qr-checkin')
    def post(self, request):
        from hr.models import QRToken, QRScanAudit
        from hr.services import create_attendance_checkin

        token_value = request.data.get('token', '').strip()
        ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')

        def _audit(action, qr_token=None):
            QRScanAudit.objects.create(
                token=token_value,
                qr_point=qr_token.qr_point if qr_token else None,
                user=request.user,
                action=action,
                ip_address=ip,
            )

        if not token_value:
            return Response({'error': 'Недействительный QR-код'}, status=400)

        try:
            qr_token = QRToken.objects.select_related('qr_point').get(token=token_value)
        except QRToken.DoesNotExist:
            _audit(QRScanAudit.ACTION_INVALID)
            return Response({'error': 'Недействительный QR-код'}, status=400)

        if qr_token.is_expired:
            _audit(QRScanAudit.ACTION_EXPIRED, qr_token)
            return Response({'error': 'QR-код истёк, отсканируйте текущий код'}, status=410)

        if qr_token.is_used_by(request.user):
            _audit(QRScanAudit.ACTION_REPLAY, qr_token)
            return Response({'error': 'Этот QR-код уже использован'}, status=409)

        employee = getattr(request.user, 'employee_info', None)
        if not employee:
            _audit(QRScanAudit.ACTION_INVALID, qr_token)
            return Response({'error': 'Профиль сотрудника не найден'}, status=403)

        record = create_attendance_checkin(
            employee=employee,
            event_type=qr_token.event_type,
            photo_file=None,
            ip_address=ip,
            source='qr',
        )

        qr_token.used_by.add(request.user)
        _audit(QRScanAudit.ACTION_SUCCESS, qr_token)

        return Response({
            'success': True,
            'message': 'Отметка успешно создана',
            'record_id': record.pk,
            'event_type': record.event_type,
            'source': record.source,
            'timestamp': record.timestamp.isoformat(),
        }, status=201)
