"""Local development settings.

Loads kubeconfig from ~/.kube/config (the same one your `kubectl` uses) so the
backend reads from whatever cluster you're currently pointed at.

Logging in locally does a real OAuth round-trip against platform-dev.pennlabs.org
using Penn Labs' shared development client, so you need network access and a
Penn Labs account on platform-dev. There is no auth-bypass switch.
"""

import os

from .base import *  # noqa: F403,F401

DEBUG = True
SECRET_KEY = "dev-secret-key-not-for-production"
ALLOWED_HOSTS = ["*"]

# The frontend dev server proxies /api to us (see frontend/src/setupProxy.js), so
# the browser only ever talks to localhost:3000 and every request is same-origin.
# That is what makes session and CSRF cookies work, and it means CORS is no
# longer in the request path -- these settings are kept only so that pointing the
# SPA straight at :8000 (REACT_APP_API_BASE_URL) still works for API-only pokes.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
]
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# oauthlib refuses to complete a flow over plain http unless told otherwise, and
# our local callback is http://localhost:3000/...
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Penn Labs' shared development OAuth client, same credentials the other Labs
# products use locally. The redirect URI is port 3000 (the frontend dev server,
# which proxies it through to us) and must match what platform-dev has
# registered for this client -- don't change it without talking to Platform.
#
# All three can be overridden from the environment to sign in against production
# Platform instead, with an OAuth client you registered there yourself (its
# redirect URI must include http://localhost:3000/api/accounts/callback/). That
# returns your real pennkey and `*_admin` permissions, so it exercises the actual
# team-lead rule rather than the shared `engineering` account below:
#
#   LABS_PLATFORM_URL=https://platform.pennlabs.org \
#   LABS_CLIENT_ID=... LABS_CLIENT_SECRET=... ./dev.sh
PLATFORM_ACCOUNTS = {
    "CLIENT_ID": os.getenv("LABS_CLIENT_ID", "clientid"),
    "CLIENT_SECRET": os.getenv("LABS_CLIENT_SECRET", "supersecretclientsecret"),
    "PLATFORM_URL": os.getenv(
        "LABS_PLATFORM_URL", "https://platform-dev.pennlabs.org"
    ),
    "REDIRECT_URI": os.getenv(
        "LABS_REDIRECT_URI", "http://localhost:3000/api/accounts/callback/"
    ),
    "ADMIN_PERMISSION": "dashboard_admin",
    "CUSTOM_ADMIN": False,
}

# Local sign-in lands you on platform-dev's shared test account, not your own
# PennKey: the shared development OAuth client above authenticates everyone as
# `engineering` (Engineering Student / engineering@upenn.edu, pennid 1000). Your
# real pennkey only comes back from *production* Platform, so an allowlist of
# real pennkeys can never match locally, and every local login would land on
# "You don't have access yet".
#
# Adding it here rather than to base.py's default is the whole point: this module
# is never loaded in production (DJANGO_SETTINGS_MODULE selects
# dashboard.settings.production there), so a shared test account cannot be
# granted access to the real dashboard by accident.
#
# `+ [...]` keeps whatever base.py resolved -- including anything set via the
# DASHBOARD_ALLOWED_USERS env var -- so this only ever widens local access.
DASHBOARD_ALLOWED_USERS = DASHBOARD_ALLOWED_USERS + ["engineering"]  # noqa: F405

# False -> use ~/.kube/config; True -> use the in-cluster ServiceAccount token.
K8S_IN_CLUSTER = False
