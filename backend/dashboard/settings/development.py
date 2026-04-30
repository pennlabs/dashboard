"""Local development settings.

Loads kubeconfig from ~/.kube/config (the same one your `kubectl` uses) so the
backend reads from whatever cluster you're currently pointed at.
"""

from .base import *  # noqa: F403,F401

DEBUG = True
SECRET_KEY = "dev-secret-key-not-for-production"
ALLOWED_HOSTS = ["*"]

# CORS: allow the React dev server to call us with credentials.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
]
CORS_ALLOW_CREDENTIALS = True

# False -> use ~/.kube/config; True -> use the in-cluster ServiceAccount token.
K8S_IN_CLUSTER = False
