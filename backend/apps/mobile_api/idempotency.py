import functools

from rest_framework.response import Response

from .models import IdempotencyKey


def idempotent(endpoint_name):
    """
    Декоратор для view-методов (post/put/patch), принимающих заголовок
    Idempotency-Key. Если ключ уже был обработан для этого пользователя
    и эндпоинта — возвращает закешированный ответ вместо повторного
    выполнения логики. Кешируются только успешные ответы (2xx).

    Использование:
        @idempotent('attendance-checkin')
        def post(self, request):
            ...
    """
    def decorator(view_method):
        @functools.wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            key = request.headers.get('Idempotency-Key')

            if not key:
                return view_method(self, request, *args, **kwargs)

            existing = IdempotencyKey.objects.filter(
                key=key, user=request.user, endpoint=endpoint_name,
            ).first()
            if existing is not None:
                return Response(existing.response_body, status=existing.status_code)

            response = view_method(self, request, *args, **kwargs)

            if 200 <= response.status_code < 300:
                from django.db import IntegrityError
                try:
                    IdempotencyKey.objects.create(
                        key=key,
                        user=request.user,
                        endpoint=endpoint_name,
                        status_code=response.status_code,
                        response_body=response.data,
                    )
                except IntegrityError:
                    pass  # уже создан параллельным запросом — не критично

            return response

        return wrapper

    return decorator