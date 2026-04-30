"""Production settings, used when the backend runs inside the cluster.

This file is kept as a deliverable artifact even though we deploy locally for
the course demo -- it shows what would change when running inside K8s:
  - Read kubeconfig from the in-cluster ServiceAccount token mount.
  - Tighten CORS to the public domain.
  - Read SECRET_KEY from env (so it can come from a Kubernetes Secret).
"""

import os

from .base import *  # noqa: F403,F401

DEBUG = False
SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-default-secret-key")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "dashboard.pennlabs.org").split(",")

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "https://dashboard.pennlabs.org",
]
CORS_ALLOW_CREDENTIALS = True

# True when running inside K8s; the backend's pod ServiceAccount provides creds.
K8S_IN_CLUSTER = os.getenv("K8S_IN_CLUSTER", "true").lower() == "true"
