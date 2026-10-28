"""
Base settings for SafeHaul project.
Common configuration shared between local and production environments.
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", "*", ".onrender.com"]),
    SECRET_KEY=(str, "django-insecure-default-change-in-production"),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    REDIS_URL=(str, ""),
    MAPBOX_ACCESS_TOKEN=(str, ""),
    ENABLE_ROUTE_CACHE=(bool, False),
    CORS_ALLOW_ALL_ORIGINS=(bool, True),
    CORS_ALLOWED_ORIGINS=(list, [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://weather-aware-truck-routing-sandy.vercel.app",
    ]),
)

# Read .env file from project root if it exists
root_env = BASE_DIR.parent / ".env"
if root_env.exists():
    environ.Env.read_env(root_env)
backend_env = BASE_DIR / ".env"
if backend_env.exists():
    environ.Env.read_env(backend_env)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    # Local apps
    "safehaul",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
_db_url = env("DATABASE_URL", default="").strip()
if _db_url:
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework configuration
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "EXCEPTION_HANDLER": "safehaul.views.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
        "analyze": "60/min",
        "geocode": "120/min",
    },
}

# CORS Configuration
CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=True)
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://weather-aware-truck-routing-sandy.vercel.app",
    ],
)
CORS_ALLOW_CREDENTIALS = False

# Cache Configuration
# SafeHaul custom ResilientCache wrapper fallback:
# In test environments or when REDIS_URL is not provided, use LocMemCache.
# In live runtime with REDIS_URL, use django_redis so ResilientCache can manage Redis failovers.
import sys

IS_TESTING = "pytest" in sys.modules or any("pytest" in arg or "test" in arg for arg in sys.argv)
REDIS_URL = env("REDIS_URL")

if REDIS_URL and not IS_TESTING:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "SOCKET_CONNECT_TIMEOUT": 5,
                "SOCKET_TIMEOUT": 5,
            },
        },
        "locmem": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "safehaul-fallback-cache",
        },
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "safehaul-local-memory-cache",
        },
        "locmem": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "safehaul-fallback-cache",
        },
    }

# SafeHaul specific external service constants
MAPBOX_ACCESS_TOKEN = env("MAPBOX_ACCESS_TOKEN")
ENABLE_ROUTE_CACHE = env("ENABLE_ROUTE_CACHE")
