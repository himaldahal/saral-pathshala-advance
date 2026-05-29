from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-kfdpfxhoy55ivg**iu8qpu=%f5ndri^8d)0j^#du)(xq8%$_ub'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

# Application definition
MY_APPS = [
    'apps.cauth',
    'apps.pages',
    'apps.exam',
]

EXTERNAL_APPS = ['tinymce']

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
            ],
        },
    },
]

WSGI_APPLICATION = 'sp.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
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
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Option A: In-memory (fast, single process)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "exam-portal-cache",
        "TIMEOUT": 300,
        "OPTIONS": {
            "MAX_ENTRIES": 2000,
        },
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