"""Base Django settings shared by dev and prod.

Notable simplifications vs. a typical Django app:
  - No database is configured here. The dashboard reads live from the K8s
    API, so we use the in-memory dummy backend. Subclasses (production.py)
    can swap this out if persistence is ever needed again.
  - No auth backends. For the course/local demo all endpoints are open;
    production deployment would re-add Penn Labs OAuth via
    `django-labs-accounts`.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    # auth + contenttypes are required by Django REST Framework's request
    # machinery even when we set `DEFAULT_PERMISSION_CLASSES = [AllowAny]`.
    # No tables are ever created since we use the dummy DB backend.
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "deployments",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "dashboard.urls"
WSGI_APPLICATION = "dashboard.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# We don't use Django's ORM, so the dummy backend is enough to keep Django happy.
DATABASES = {
    "default": {"ENGINE": "django.db.backends.dummy"},
}

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
}
