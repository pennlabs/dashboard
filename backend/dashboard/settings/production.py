import os

from .base import *  # noqa: F403,F401

DEBUG = False
SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-default-secret-key")
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "https://dashboard.pennlabs.org",
]
CORS_ALLOW_CREDENTIALS = True
K8S_IN_CLUSTER = os.getenv("K8S_IN_CLUSTER", "false").lower() == "true"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", ""),
        "USER": os.getenv("POSTGRES_USER", ""),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", ""),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}
