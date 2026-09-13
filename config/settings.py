"""Environment-configured settings; SQLite and a shared database cache for one host."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("Set DJANGO_SECRET_KEY or enable DJANGO_DEBUG for local development")
    SECRET_KEY = "development-only-fuel-route-do-not-deploy"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "routes",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "route_cache",
        "OPTIONS": {"MAX_ENTRIES": 20000},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "30/min"},
    "EXCEPTION_HANDLER": "routes.exceptions.exception_handler",
    "UNAUTHENTICATED_USER": None,
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 8192
OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org").rstrip("/")
GEOCODING_BASE_URL = os.getenv("GEOCODING_BASE_URL", "https://nominatim.openstreetmap.org").rstrip("/")
GEOCODING_USER_AGENT = os.getenv("GEOCODING_USER_AGENT", "FuelRouteAssessment/1.0 (Django route planner)")
OVERPASS_BASE_URL = os.getenv("OVERPASS_BASE_URL", "https://overpass-api.de/api/interpreter")
TILE_URL = os.getenv("TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
CACHE_TIMEOUT = int(os.getenv("CACHE_TIMEOUT", "86400"))
GEOCODING_CACHE_TIMEOUT = int(os.getenv("GEOCODING_CACHE_TIMEOUT", "2592000"))
MAX_STATION_ROUTE_DISTANCE_MILES = float(os.getenv("MAX_STATION_ROUTE_DISTANCE_MILES", "5"))
VEHICLE_MAX_RANGE_MILES = os.getenv("VEHICLE_MAX_RANGE_MILES", "500")
VEHICLE_MPG = os.getenv("VEHICLE_MPG", "10")
HTTP_TIMEOUT = (5, 30)
LOCK_DIR = BASE_DIR / ".locks"
SECURE_CONTENT_TYPE_NOSNIFF = True
# OSM tile policy requires a Referer. Send only this site's origin cross-origin.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "false").lower() == "true"
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
