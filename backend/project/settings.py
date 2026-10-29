"""
Django settings for TRC BPM project.
"""


import os
import sys
from pathlib import Path
from decouple import config, Csv
from datetime import timedelta
from celery.schedules import crontab


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))

LOGIN_URL = '/account/auth'

SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', default=True, cast=bool)
FINANCES_MENU_ENABLED = config('FINANCES_MENU_ENABLED', default=False, cast=bool)

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='127.0.0.1,localhost,0.0.0.0,10.0.2.2',
    cast=Csv(),
)
if DEBUG:
    for host in ('127.0.0.1', 'localhost', '0.0.0.0'):
        if host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)

CSRF_TRUSTED_ORIGINS = config('TRUSTED_ORIGINS', cast=Csv())


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_celery_results',
    'django_celery_beat',
    'mptt',
    'django_mptt_admin',
    'betterforms',

    'account',
    'dashboard',
    'documents',
    'ecopark',
    'finances',
    'hr',
    'purchases',
    'reports',
    'requistions',
    'tasks',
    'tenants',
    'tickets',
    'plans',
    'addits',
    'enbek',
    'onec',
    'esigner',
    'mobile_api',
    'audit',
    'rest_framework',
    'drf_spectacular',
    'django_filters',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'account.auth_middleware.LoginRequiredMiddleware',
    'audit.middleware.AuditMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'account.language_middleware.LanguageMiddleware',
]

ROOT_URLCONF = 'project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'account.context_processors.info',
            ],
        },
    },
]

WSGI_APPLICATION = 'project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': config('POSTGRES_ENGINE', default='django.db.backends.sqlite3'),
        'NAME': config('POSTGRES_DB', default=BASE_DIR + '/' + 'db.sqlite3'),
        'USER': config('POSTGRES_USER', default='user'),
        'PASSWORD': config('POSTGRES_PASSWORD', default='password'),
        'HOST': config('POSTGRES_HOST', default='localhost'),
        'PORT': config('POSTGRES_PORT', default='5432'),
    }
}

AUTH_USER_MODEL = 'account.UserAccount'

# Password validation
# https://docs.djangoproject.com/en/4.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/account/auth'

SESSION_COOKIE_AGE = 60*60*24*30

DISABLE_DARK_MODE = True

# Internationalization
# https://docs.djangoproject.com/en/4.0/topics/i18n/

LANGUAGE_CODE = 'ru'

TIME_ZONE = config('TZ')

USE_I18N = True

USE_TZ = True

DATE_FORMAT = "d.m.Y"


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.0/howto/static-files/

STATIC_URL = '/static/'
STATIC_DIR = os.path.join(BASE_DIR, 'static')
STATICFILES_DIRS = [STATIC_DIR]

STATIC_ROOT = os.path.join(BASE_DIR, 'assets')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
# https://docs.djangoproject.com/en/4.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'




# SMTP (Cloud24 / Outlook / любой SMTP)
# Cloud24: mail.cloud24.kz:587 + TLS | M365: smtp.office365.com:587 + TLS
EMAIL_HOST = config('EMAIL_HOST', default='mail.cloud24.kz')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
_default_from = config('DEFAULT_FROM_EMAIL', default='') or EMAIL_HOST_USER or 'noreply@metrix.com.ai'
DEFAULT_FROM_EMAIL = _default_from
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=30, cast=int)
# Без пароля — письма в консоль (удобно для локальной разработки)
_email_backend_default = (
    'django.core.mail.backends.smtp.EmailBackend'
    if EMAIL_HOST_PASSWORD
    else 'django.core.mail.backends.console.EmailBackend'
)
EMAIL_BACKEND = config('EMAIL_BACKEND', default=_email_backend_default)
# Публичный URL для ссылок в письмах (логин портала и т.п.)
PUBLIC_SITE_URL = config('PUBLIC_SITE_URL', default='').rstrip('/')
# macOS / системный Python часто без корневых CA — подставляем certifi
try:
    import certifi as _certifi
    import os as _os
    _os.environ.setdefault('SSL_CERT_FILE', _certifi.where())
    _os.environ.setdefault('REQUESTS_CA_BUNDLE', _certifi.where())
except ImportError:
    pass


REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DATETIME_FORMAT': "%d.%m.%Y, %H:%M",
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=90),
    'ROTATE_REFRESH_TOKENS': True,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'TRC BPM API',
    'DESCRIPTION': 'MetriX BPM — Tasks, HR, Finances, 1C Integration',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SERVE_PERMISSIONS': ['rest_framework.permissions.AllowAny'],
    'SERVE_AUTHENTICATION': [],
}

# CELERY
CELERY_BROKER_URL = config('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_BEAT_SCHEDULE = {
    'sync_counterparties_every_4_hours': {
        'task': 'sync_counterparties_task',
        'schedule': timedelta(hours=4),
    },
    'sync_onec_finances_every_4_hours': {
        'task': 'sync_onec_all_task',
        'schedule': timedelta(hours=4),
    },
    'sync-enbek-every-6-hours': {
        'task': 'hr.tasks.sync_enbek_data',
        'schedule': crontab(minute=0, hour='*/6'),
    },
    'hr-check-expirations': {
        'task': 'hr.tasks.hr_check_expirations',
        'schedule': crontab(hour=6, minute=0),
    },
    'esigner-poll-pending': {
        'task': 'esigner_poll_pending_signings_task',
        'schedule': 600,
    },
    'tasks-cleanup-bin-daily': {
        'task': 'tasks.cleanup_bin',
        'schedule': crontab(hour=3, minute=0),
        'kwargs': {'days': 30},
    },
    'tickets-sla-escalation': {
        'task': 'tickets.sla_escalation',
        'schedule': crontab(hour='*/4', minute=0),
    },
    # Обходы и отметки демо-аккаунта привязаны к дате, поэтому без
    # ежедневного переноса проверяющий из App Review видит пустые экраны.
    'mobile-refresh-review-demo': {
        'task': 'mobile_api.refresh_review_demo',
        'schedule': crontab(hour=0, minute=10),
    },
    'account-cleanup-notifications-daily': {
        'task': 'account.cleanup_notifications',
        'schedule': crontab(hour=2, minute=0),
        'kwargs': {'days': 60},
    },
    'account-expire-temporary-accesses': {
        'task': 'account.expire_temporary_accesses',
        'schedule': crontab(minute=0, hour='*/1'),
    },
    # Курсы НБ РК отключены — в интерфейсе все суммы в ₸
    # 'fetch-exchange-rates-daily': {
    #     'task': 'finances.tasks.fetch_exchange_rates',
    #     'schedule': crontab(hour=14, minute=0),
    # },
}

CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'


#ADDIT
MPTT_ADMIN_LEVEL_INDENT = 20
X_FRAME_OPTIONS = 'ALLOWALL'

ONEC_URL = config('ONEC_URL', default='')
ALTERNATE_ONEC_URL = config('ALTERNATE_ONEC_URL', default='')

# 1C Full Client (client_1c)
ONE_C_BASE_URL = config('ONE_C_BASE_URL', default='')
ONE_C_BASIC_AUTH_USER = config('ONE_C_BASIC_AUTH_USER', default='')
ONE_C_BASIC_AUTH_PASSWORD = config('ONE_C_BASIC_AUTH_PASSWORD', default='')
ONE_C_API_USER = config('ONE_C_API_USER', default='')
ONE_C_API_PASSWORD = config('ONE_C_API_PASSWORD', default='')
ONE_C_SYNC_ENABLED = config('ONE_C_SYNC_ENABLED', default=True, cast=bool)
ONE_C_SYNC_SINCE_DAYS = config('ONE_C_SYNC_SINCE_DAYS', default=90, cast=int)
ONE_C_TIMEOUT = config('ONE_C_TIMEOUT', default=30, cast=int)
ONE_C_VERIFY_SSL = config('ONE_C_VERIFY_SSL', default=True, cast=bool)

ENBEK_BASE_URL = config('ENBEK_BASE_URL', default='http://web:8000/api/enbek')
ENBEK_USERNAME = config('ENBEK_USERNAME', default='test')
ENBEK_PASSWORD = config('ENBEK_PASSWORD', default='test')
ENBEK_TIMEOUT = config('ENBEK_TIMEOUT', default=10, cast=int)

# ONLYOFFICE Document Server (серверное редактирование документов)
# DS уже поднят на office.metrix.com.ai; секрет — общий с сервером (HS256).
# DS_PUBLIC_URL — адрес Document Server для браузера (откуда грузится api.js).
# BACKEND_INTERNAL_URL — адрес Django, доступный Document Server'у для скачивания
# файла и callback (ДОЛЖЕН быть публичным — DS внешний). Пусто — из запроса.
ONLYOFFICE_DS_PUBLIC_URL = config('ONLYOFFICE_DS_PUBLIC_URL', default='https://office.metrix.com.ai')
ONLYOFFICE_BACKEND_INTERNAL_URL = config('ONLYOFFICE_BACKEND_INTERNAL_URL', default='')
ONLYOFFICE_JWT_SECRET = config('ONLYOFFICE_JWT_SECRET', default='s4x3XgJV8c6CwHlgu3WkUEdaiTwGjdBW')
ONLYOFFICE_JWT_ENABLED = config('ONLYOFFICE_JWT_ENABLED', default=True, cast=bool)
ONLYOFFICE_CALLBACK_TIMEOUT = config('ONLYOFFICE_CALLBACK_TIMEOUT', default=30, cast=int)
ONLYOFFICE_ALLOWED_DOWNLOAD_HOSTS = config(
    'ONLYOFFICE_ALLOWED_DOWNLOAD_HOSTS',
    default='',
    cast=Csv(),
)

ESIGNER_URL = config('ESIGNER_URL', default='https://esigner.kz/back')
ESIGNER_SIGN_BASE_URL = config('ESIGNER_SIGN_BASE_URL', default='https://sign.avantage.one')
ESIGNER_CLIENT_ID = config('ESIGNER_CLIENT_ID', default='')
ESIGNER_SECRET_KEY = config('ESIGNER_SECRET_KEY', default='')
ESIGNER_COMPANY_ID = config('ESIGNER_COMPANY_ID', default=0, cast=int)
ESIGNER_FOLDER_ID = config('ESIGNER_FOLDER_ID', default='')
ESIGNER_TIMEOUT = config('ESIGNER_TIMEOUT', default=30, cast=int)
ESIGNER_WEBHOOK_SECRET = config('ESIGNER_WEBHOOK_SECRET', default='')

ATTENDANCE_DISABLED_TYPES = ['lunch_start', 'lunch_end']
ATTENDANCE_MAX_EDIT_DAYS = 30
