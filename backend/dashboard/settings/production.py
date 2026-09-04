"""Production settings, used when the backend runs inside the cluster.

Differences from development:
  - Read kubeconfig from the in-cluster ServiceAccount token mount.
  - Tighten CORS/CSRF to the public domain and require secure cookies.
  - Read secrets from env, so they can come from Vault via a Kubernetes Secret.
  - Talk to the real platform.pennlabs.org rather than platform-dev.

Required environment (see `secret: "dashboard"` in k8s/main.ts):
  SECRET_KEY           signs session cookies
  LABS_CLIENT_ID       OAuth client issued by Platform
  LABS_CLIENT_SECRET   ditto
  LABS_REDIRECT_URI    https://dashboard.pennlabs.org/api/accounts/callback/
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403,F401

DEBUG = False

# No unsafe fallback: this key signs session cookies, so a default value would
# let anyone forge a logged-in session. Fail at startup instead.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY must be set in production -- it signs session cookies."
    )

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "dashboard.pennlabs.org").split(",")

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "https://dashboard.pennlabs.org",
]
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = ["https://dashboard.pennlabs.org"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# DLA reads CLIENT_ID, CLIENT_SECRET and REDIRECT_URI from the LABS_* environment
# variables by default, and PLATFORM_URL already defaults to the production
# platform.pennlabs.org -- so only the permission settings need restating here.
PLATFORM_ACCOUNTS = {
    "ADMIN_PERMISSION": "dashboard_admin",
    "CUSTOM_ADMIN": False,
}

# True when running inside K8s; the backend's pod ServiceAccount provides creds.
K8S_IN_CLUSTER = os.getenv("K8S_IN_CLUSTER", "true").lower() == "true"
