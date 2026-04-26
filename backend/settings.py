"""
Django settings for Ethereal Voice Agent Platform.
"""

import os
from pathlib import Path
from datetime import timedelta

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY: Use env var in production. Falls back to dev key only if missing.
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-dev-key-change-in-production'
)

DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')


# Application definition

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party
    'rest_framework',
    'corsheaders',
    'channels',
    
    # Local Apps
    'apps.tenants',
    'apps.users',
    'apps.campaigns',
    'apps.calls',
    'apps.billing',
    'apps.ai_engine',
    'apps.websockets',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # Must be before CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # ↓ Sets thread-local tenant context for RegionRouter (after auth so JWT is available)
    'apps.tenants.middleware.TenantContextMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ── CORS ─────────────────────────────────────────────────────
# Allow Next.js frontend origin. Add production domain in env.
CORS_ALLOWED_ORIGINS = os.environ.get(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:3000,http://127.0.0.1:3000'
).split(',')
CORS_ALLOW_CREDENTIALS = True

ROOT_URLCONF = 'backend.urls'

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

WSGI_APPLICATION = 'backend.wsgi.application'
ASGI_APPLICATION = 'backend.asgi.application'

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
        },
    },
}

# ── Celery ───────────────────────────────────────────────
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
# Prevent tasks from running eagerly in tests; use CELERY_TASK_ALWAYS_EAGER=True in test settings
CELERY_TASK_ALWAYS_EAGER = False

# ── Celery Beat — scheduled tasks ─────────────────────────────────────────────
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    'realtime-billing': {
        'task': 'apps.billing.tasks.calculate_realtime_billing',
        'schedule': 10.0,  # every 10 seconds
    },
}

AUTH_USER_MODEL = 'users.User'
# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

def _pg(env_prefix: str, db_name_default: str) -> dict:
    """Build a Postgres DB config from env vars with SQLite fallback for local dev."""
    pg_host = os.environ.get(f'{env_prefix}_HOST', '')
    if pg_host:
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get(f'{env_prefix}_NAME', db_name_default),
            'USER': os.environ.get(f'{env_prefix}_USER', 'postgres'),
            'PASSWORD': os.environ.get(f'{env_prefix}_PASSWORD', ''),
            'HOST': pg_host,
            'PORT': os.environ.get(f'{env_prefix}_PORT', '5432'),
            'OPTIONS': {
                # Force UTC session timezone; let Django handle tz-aware datetimes.
                'options': '-c timezone=UTC',
            },
            'CONN_MAX_AGE': 60,
        }
    # Local dev fallback — SQLite (no Postgres installed)
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / f'db_{db_name_default}.sqlite3',
    }


DATABASES = {
    # Global DB — tenants, users, auth tables (always default)
    'default': _pg('DB_GLOBAL', 'global'),
    # India shard — target: ap-south-1 RDS
    'india_db': _pg('DB_INDIA', 'india'),
    # UK shard — target: eu-west-2 RDS
    'uk_db': _pg('DB_UK', 'uk'),
}

DATABASE_ROUTERS = ['backend.db_routers.RegionRouter']

# ── REST Framework ───────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        # Session auth kept for browser-based admin/dev access
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# ── SimpleJWT ────────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    # Custom claim: embed tenant_id so we can enforce isolation without a DB hit
    'TOKEN_OBTAIN_SERIALIZER': 'apps.users.serializers.TenantTokenObtainPairSerializer',
}

# ── Logging ──────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'apps': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
        'channels': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'

# ── Default Primary Key ──────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
