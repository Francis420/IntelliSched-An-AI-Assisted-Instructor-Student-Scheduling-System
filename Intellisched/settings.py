from pathlib import Path
from decouple import config
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')  # now loaded from .env

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = ["72.61.112.93",
 "srv1247444.hstgr.cloud",
"intellisched.online",
 "www.intellisched.online",
 "localhost", "127.0.0.1"]

CSRF_TRUSTED_ORIGINS = [
 "http://72.61.112.93",
 "http://srv1247444.hstgr.cloud",
]

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework.authtoken',

    'tailwind',
    'theme',
    'django_browser_reload',
    'channels',

    'core.apps.CoreConfig',
    'instructors.apps.InstructorsConfig',
    'scheduling.apps.SchedulingConfig',
    'adminpanel',
    'authapi',
    'aimatching.apps.AimatchingConfig',
    'scheduler.apps.SchedulerConfig',
    'auditlog',
]


CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'


ASGI_APPLICATION = "Intellisched.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
        },
    },
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
}

TAILWIND_APP_NAME = 'theme'
INTERNAL_IPS = ['127.0.0.1']

NPM_BIN_PATH = "C:/Program Files/nodejs/npm.cmd"

from pathlib import Path

LLAMA_CPP_PATH = str(BASE_DIR / "aimatching" / "models" / "llama-run.exe")
MISTRAL_MODEL_PATH = str(BASE_DIR / "aimatching" / "models" / "mistral-7b-instruct-v0.1.Q6_K.gguf")


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'Intellisched.urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.csrf',
            ],
        },
    },
]

WSGI_APPLICATION = 'Intellisched.wsgi.application'


# Database - using MySQL via .env
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='3307'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        }
    }
}


# Password validation
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


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'core.User'

LOGIN_URL = '/auth/login/'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'francisjonel.balagusa@evsu.edu.ph'
EMAIL_HOST_PASSWORD = 'zteg bvcv jxqb oiwi'
DEFAULT_FROM_EMAIL = f"IntelliSched Support <{EMAIL_HOST_USER}>"

LOGGING = {
'version': 1,
'disable_existing_loggers': False,
'handlers': {
'file': {
'level': 'ERROR',
'class': 'logging.FileHandler',
'filename': os.path.join(BASE_DIR, 'logs', 'django-errors.log'),
},
},
'loggers': {
'django': {
'handlers': ['file'],
'level': 'ERROR',
'propagate': True,
},
},
}
