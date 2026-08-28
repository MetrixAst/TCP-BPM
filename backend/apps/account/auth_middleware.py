from django.conf import settings
from django.shortcuts import redirect

PUBLIC_PREFIXES = (
    '/account/auth',
    '/account/login',
    '/account/mobile/',
    '/api/',
    '/onec/api/',
    '/admin/',
    '/static/',
    '/media/',
    '/.well-known/',
)


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            not self._is_public(request.path)
            and not request.user.is_authenticated
            and not request.META.get('HTTP_AUTHORIZATION')
        ):
            login_url = getattr(settings, 'LOGIN_URL', '/account/auth/')
            return redirect(f'{login_url}?next={request.path}')
        return self.get_response(request)

    @staticmethod
    def _is_public(path: str) -> bool:
        return any(path.startswith(p) for p in PUBLIC_PREFIXES)