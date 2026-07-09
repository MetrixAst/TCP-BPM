from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import NotificationIndicator, PushToken
from account.role_permissions import MenuItem

from .serializers import ProfileSerializer, PushTokenSerializer


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