from pathlib import Path
from celery.schedules import crontab

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-kfdpfxhoy55ivg**iu8qpu=%f5ndri^8d)0j^#du)(xq8%$_ub'

DEBUG = True
IS_PRODUCTION = False

if IS_PRODUCTION:
    ALLOWED_HOSTS = ['168.144.144.61','exam.saralpathshala.com', "cdn.saralpathshala.com"]
else:
    ALLOWED_HOSTS = ['localhost','127.0.0.1']

# Application definition
MY_APPS = [
    'apps.cauth',
    'apps.pages',
    'apps.exam',
]

EXTERNAL_APPS = ['tinymce','django_celery_beat']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
] + MY_APPS + EXTERNAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
]

ROOT_URLCONF = 'sp.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR/'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.pages.context_processors.site_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'sp.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases
if not IS_PRODUCTION:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else: 
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "saralpathshala",
            "USER": "saraluser",
            "PASSWORD": "@Himal_2060",
            "HOST": "127.0.0.1",
            "PORT": "5432",
            "CONN_MAX_AGE":300,
            "connect_timeout": 10,
        }
    }

# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators
AUTH_USER_MODEL = 'cauth.User' 

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kathmandu'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
if IS_PRODUCTION:
    MEDIA_ROOT = "/var/www/cdn/media"
    MEDIA_URL = "https://cdn.saralpathshala.com/media/"
else:
    MEDIA_ROOT = BASE_DIR / 'media'
    MEDIA_URL = '/media/'

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}
# ─────────────────────────────────────────────────────────────────────────────
# TINYMCE
# ─────────────────────────────────────────────────────────────────────────────
TINYMCE_DEFAULT_CONFIG = {
    "height": 300,
    "menubar": False,
    "plugins": (
        "advlist autolink lists link image charmap preview "
        "anchor searchreplace visualblocks code fullscreen "
        "insertdatetime media table codesample"
    ),
    "toolbar": (
        "undo redo | styles | bold italic underline | "
        "alignleft aligncenter alignright | "
        "bullist numlist | codesample code | link image | fullscreen"
    ),
    "images_upload_url":'/astabakraa/sp/upload_images/',
    "codesample_global_prismjs": True,
    "codesample_languages": [
        {"text": "Python",     "value": "python"},
        {"text": "JavaScript", "value": "javascript"},
        {"text": "C",          "value": "c"},
        {"text": "C++",        "value": "cpp"},
        {"text": "Java",       "value": "java"},
        {"text": "SQL",        "value": "sql"},
        {"text": "Bash",       "value": "bash"},
    ],
    # Preserve MathJax dollar-sign delimiters
    "extended_valid_elements": "span[*]",
    "protect": [r"/\$.*?\$/"],   # don't escape $ inside content
}
 
TINYMCE_SPELLCHECKER = False

# Authentication Settings
LOGIN_URL = '/auth/login/'

# Google reCAPTCHA v3 configurations
# (Defaults are set to Google's public test keys. Replace with actual keys in production)
RECAPTCHA_SITE_KEY = '6LcEkVkrAAAAAKxoGK7mTXaPyg3XV3wDN5XxxudF'
RECAPTCHA_SECRET_KEY = '6LcEkVkrAAAAAFXodlMavHGj5BsQ-FYWjmuyMvrx'

akash_sms_auth_token = '6eb4a353603d0ebde90ebe74ed2f390bcacc165bdecabfc606b97a41539c2a81'

# ── SMTP Email Server Configuration ───────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'auth.saralpathshala@gmail.com'
# EMAIL_HOST_PASSWORD = '@Himal_9869049923'
EMAIL_HOST_PASSWORD = 'xukr ggif byqa yaqk'
DEFAULT_FROM_EMAIL = 'Saral Pathshala <auth.saralpathshala@gmail.com>'
SERVER_EMAIL = 'auth.saralpathshala@gmail.com'

# Redis as broker + result backend
CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Kathmandu'

CELERY_BEAT_SCHEDULE = {
    'process-sms-queue': {
        'task': 'apps.cauth.tasks.process_sms_queue',
        'schedule': 10.0,  # every 60 seconds
    },
    'process-email-queue': {
        'task': 'apps.cauth.tasks.process_email_queue',
        'schedule': 10.0,
    },
}

if IS_PRODUCTION:
    SECURE_SSL_REDIRECT = True
else:
    SECURE_SSL_REDIRECT = False
