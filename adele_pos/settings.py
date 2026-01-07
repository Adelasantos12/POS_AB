from pathlib import Path
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Lee la SECRET_KEY de una variable de entorno. Es CRÍTICO que esto se configure en producción.
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-default-secret-key-for-development')

# DEBUG se desactiva si la variable ENVIRONMENT es 'production'.
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')
DEBUG = ENVIRONMENT != 'production'

# --- Configuración de Hosts ---
# En producción, lee los hosts permitidos de la variable de entorno DJANGO_ALLOWED_HOSTS.
# Esta variable debe ser una lista de dominios separados por comas.
# Ejemplo: 'posboutique.up.railway.app,www.miotraapp.com'
ALLOWED_HOSTS_STRING = os.environ.get('DJANGO_ALLOWED_HOSTS')
if ALLOWED_HOSTS_STRING:
    ALLOWED_HOSTS = ALLOWED_HOSTS_STRING.split(',')
else:
    # Para desarrollo local, permite cualquier host.
    ALLOWED_HOSTS = ['*'] if DEBUG else []

# --- Configuración de CSRF ---
# Para peticiones seguras (HTTPS), Django necesita saber qué dominios son de confianza.
# Lee los orígenes de confianza de la misma variable DJANGO_ALLOWED_HOSTS.
CSRF_TRUSTED_ORIGINS = []
if ALLOWED_HOSTS_STRING:
    # Se debe incluir el esquema (https://) para cada dominio.
    for host in ALLOWED_HOSTS_STRING.split(','):
        CSRF_TRUSTED_ORIGINS.append(f"https://{host.strip()}")


INSTALLED_APPS = [
    'boutique.apps.BoutiqueConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
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
    DATABASES = {
        'default': dj_database_url.config(conn_max_age=600, ssl_require=True)
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

LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
