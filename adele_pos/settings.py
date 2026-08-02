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
    'django_ratelimit',
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
    'boutique.middleware.RequestIDMiddleware',
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
                'boutique.context_processors.tienda_globals',
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
if not DEBUG:
    # CompressedStaticFilesStorage: compresses files but does NOT build a strict
    # manifest. CompressedManifest* crashes on Django 5.x admin CSS cross-references.
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
        },
    }
    # Compat shim: django-cloudinary-storage reads this legacy attribute on Django 5.x.
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# --- Configuración de Archivos Media ---
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --- Cloudinary para fotos de productos persistentes en producción ---
# IMPORTANTE: NO agregamos cloudinary_storage a INSTALLED_APPS porque su
# comando collectstatic personalizado salta copy_file cuando no usa
# StaticCloudinaryStorage, lo que rompe el post-procesado de whitenoise.
# El backend MediaCloudinaryStorage funciona sin estar en INSTALLED_APPS.
CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL', '')
if CLOUDINARY_URL:
    try:
        import cloudinary as _cloudinary
        _cloudinary.config(cloudinary_url=CLOUDINARY_URL)
        # Solo sobreescribir el backend de media (fotos), no el de static.
        if not DEBUG:
            STORAGES['default'] = {
                'BACKEND': 'cloudinary_storage.storage.MediaCloudinaryStorage',
            }
        else:
            STORAGES = {
                'default': {
                    'BACKEND': 'cloudinary_storage.storage.MediaCloudinaryStorage',
                },
                'staticfiles': {
                    'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
                },
            }
    except Exception as _e:
        import logging as _logging
        _logging.error(f'Cloudinary setup error: {_e}')

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'index'
LOGOUT_REDIRECT_URL = 'index'

# --- Cookies y seguridad HTTP ---
# SameSite=Lax en todos los entornos: bloquea envío de cookies en
# navegaciones cross-site iniciadas por terceros (POST desde otro dominio).
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_HTTPONLY = True   # JS no puede leer la cookie de sesión
X_FRAME_OPTIONS = 'DENY'         # Previene clickjacking en todos los entornos

# Railway termina TLS en su proxy y reenvía HTTP a Django.
# SECURE_SSL_REDIRECT=True causaría redirect loop; Railway ya fuerza HTTPS externamente.
# SECURE_PROXY_SSL_HEADER hace que Django trate la petición como segura basándose en el header X-Forwarded-Proto.
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # W004 y W008 se silencian porque Railway maneja HSTS y SSL-redirect a nivel de proxy.
    SILENCED_SYSTEM_CHECKS = ['security.W004', 'security.W008']

# django-ratelimit: E003/W001 silenciados porque Railway usa Gunicorn con 1
# worker (start.sh no pasa --workers). Con 1 worker, LocMemCache es efectivo
# para rate limiting. Si se añaden workers, migrar a Redis.
SILENCED_SYSTEM_CHECKS = getattr(locals(), 'SILENCED_SYSTEM_CHECKS', []) + [
    'django_ratelimit.E003',
    'django_ratelimit.W001',
]

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
