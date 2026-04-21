"""
Django settings for TRC BPM project.
"""


import os
import sys
from pathlib import Path
from decouple import config, Csv
from datetime import timedelta


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))


SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

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
    'addits',
    'enbek',
    'onec',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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




# EMAIL_HOST = config('EMAIL_HOST')
# EMAIL_HOST_USER = config('EMAIL_HOST_USER')
# EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
# EMAIL_USE_TLS = True
# EMAIL_PORT = config('EMAIL_PORT')
# DEFAULT_FROM_EMAIL = EMAIL_HOST_USER


REST_FRAMEWORK = {
    # 'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated', ), #IsAuthenticatedOrReadOnly
    # 'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication', ),
    # 'EXCEPTION_HANDLER': 'project.utils.custom_exception_handler',
    # 'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'DATETIME_FORMAT': "%d.%m.%Y, %H:%M", 
    # 'PAGE_SIZE': 15,
    # 'COERCE_DECIMAL_TO_STRING': False,
    # 'DEFAULT_RENDERER_CLASSES': (
    #     'rest_framework.renderers.JSONRenderer',
    # )
}

# SIMPLE_JWT = {
#     'ACCESS_TOKEN_LIFETIME': timedelta(days=30),
#     'REFRESH_TOKEN_LIFETIME': timedelta(days=35),
# }

# CELERY
CELERY_BROKER_URL = config('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = 'django-db'


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

ENBEK_BASE_URL = config('ENBEK_BASE_URL', default='http://web:8000/api/enbek')
ENBEK_USERNAME = config('ENBEK_USERNAME', default='test')
ENBEK_PASSWORD = config('ENBEK_PASSWORD', default='test')
ENBEK_TIMEOUT = config('ENBEK_TIMEOUT', default=10, cast=int)