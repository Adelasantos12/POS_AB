from pathlib import Path
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-default-secret-key-for-development')

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')
DEBUG = ENVIRONMENT != 'production'

ALLOWED_HOSTS_STRING = os.environ.get('DJANGO_ALLOWED_HOSTS')
if ALLOWED_HOSTS_STRING:
    ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_STRING.split(',')]
    if 'testserver' not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append('testserver')
else:
    ALLOWED_HOSTS = ['*', 'testserver'] if DEBUG else []

CSRF_TRUSTED_ORIGINS = []
if ALLOWED_HOSTS_STRING:
    for host in ALLOWED_HOSTS_STRING.split(','):
        h = host.strip()
        CSRF_TRUSTED_ORIGINS.append(f"https://{h}")
        CSRF_TRUSTED_ORIGINS.append(f"http://{h}")

INSTALLED_APPS = [
    'whitenoise.runserver_nostatic',
    'boutique.apps.BoutiqueConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
]

# El middleware de WhiteNoise debe ir después del de Seguridad.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'boutique.middleware.ProfileMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'adele_pos.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'adele_pos.wsgi.application'

if 'DATABASE_URL' in os.environ:
    db_ssl_require = os.environ.get('DB_SSL_REQUIRE', 'True').lower() == 'true'
    DATABASES = {
        'default': dj_database_url.config(conn_max_age=600, ssl_require=db_ssl_require)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# --- Configuración de Archivos Estáticos ---
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Prevent collectstatic from crashing when a CSS file references a missing file
WHITENOISE_MANIFEST_STRICT = False
if not DEBUG:
    # Django 4.2+ requires STORAGES dict; overridden below when Cloudinary is active.
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }
    # Compat shim: django-cloudinary-storage reads settings.STATICFILES_STORAGE
    # which no longer exists as a top-level setting in Django 5.x.
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# --- Configuración de Archivos Media ---
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --- Cloudinary para fotos persistentes en producción ---
# cloudinary_storage debe ir ANTES de django.contrib.staticfiles en INSTALLED_APPS
CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL', '')
if CLOUDINARY_URL:
    try:
        import cloudinary as _cloudinary
        _cloudinary.config(cloudinary_url=CLOUDINARY_URL)
        _sf_idx = INSTALLED_APPS.index('django.contrib.staticfiles')
        INSTALLED_APPS.insert(_sf_idx, 'cloudinary_storage')
        INSTALLED_APPS.insert(_sf_idx + 1, 'cloudinary')
        # Django 4.2+ requires STORAGES dict; DEFAULT_FILE_STORAGE is silently
        # ignored in Django 5.x.
        _static_backend = (
            'whitenoise.storage.CompressedManifestStaticFilesStorage'
            if not DEBUG else
            'django.contrib.staticfiles.storage.StaticFilesStorage'
        )
        STORAGES = {
            'default': {
                'BACKEND': 'cloudinary_storage.storage.MediaCloudinaryStorage',
            },
            'staticfiles': {
                'BACKEND': _static_backend,
            },
        }
        # Compat shim for django-cloudinary-storage which reads this legacy attribute
        STATICFILES_STORAGE = _static_backend
    except ValueError as _e:
        import logging as _logging
        _logging.error(f'Cloudinary setup error (django.contrib.staticfiles not found): {_e}')
    except Exception as _e:
        import logging as _logging
        _logging.error(f'Cloudinary setup unexpected error: {_e}')
        raise

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'index'
LOGOUT_REDIRECT_URL = 'index'

# --- Integración IA Gemini ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

# --- Logging ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'boutique': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
