from django.utils import translation

SUPPORTED_LANGS = {'ru', 'kk', 'en'}
DEFAULT_LANG = 'ru'
LANG_COOKIE = 'bpm_lang'

class LanguageMiddleware:
    """
    Saves language preference in a cookie so it persists across pages.
    Setting ?lang= stores the choice immediately — no session required.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Read incoming ?lang= parameter
        lang_param = request.GET.get('lang')
        if lang_param in SUPPORTED_LANGS:
            current_lang = lang_param
        else:
            current_lang = request.COOKIES.get(LANG_COOKIE, DEFAULT_LANG)
            if current_lang not in SUPPORTED_LANGS:
                current_lang = DEFAULT_LANG

        request.current_lang = current_lang

        # ── Активируем Django gettext для правильного перевода lazy строк ──
        translation.activate(current_lang)

        response = self.get_response(request)

        # Persist new language choice in cookie (1 year)
        if lang_param in SUPPORTED_LANGS:
            response.set_cookie(
                LANG_COOKIE,
                lang_param,
                max_age=60 * 60 * 24 * 365,
                httponly=False,
                samesite='Lax',
            )

        return response