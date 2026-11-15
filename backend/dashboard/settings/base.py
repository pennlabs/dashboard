"""Base Django settings shared by dev and prod.

Notable points about this app's shape:
  - Deployment data is never persisted. The dashboard reads live from the K8s
    API on every request. The database exists purely for authentication --
    Django's User/Group/Permission/session tables plus the OAuth token tables
    that `django-labs-accounts` (DLA) ships.
  - Auth is Penn Labs OAuth via DLA, and access is restricted to team leads.
    See `deployments/backends.py` for how a "team lead" is identified and
    `deployments/permissions.py` for how that is enforced.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    # DLA: the /accounts/ login, callback and logout views that redirect through
    # platform.pennlabs.org, plus its AccessToken/RefreshToken models.
    # Deliberately omitted: django.contrib.admin (this app has no admin site) and
    # identity.apps.IdentityConfig (only needed for backend-to-backend IPC).
    "accounts.apps.AccountsConfig",
    "deployments",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

ROOT_URLCONF = "dashboard.urls"
WSGI_APPLICATION = "dashboard.wsgi.application"
# AutoField, not BigAutoField: DLA's shipped migrations were written against
# AutoField, and a BigAutoField default makes Django want to generate an ALTER
# migration for them inside site-packages. `deployments` has no models of its
# own, so this setting affects nothing else. Platform pins the same value.
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# SQLite in every environment. Nothing here is a source of truth -- users and
# their lead status are re-fetched from Platform on each login -- so an
# ephemeral database is fine, and losing it just means everyone silently
# re-authenticates through their existing Platform SSO session. Note this is
# also why the backend runs a single replica in k8s/main.ts: with a per-pod
# database file, a session minted on one pod means nothing on another.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
}

AUTHENTICATION_BACKENDS = (
    "deployments.backends.DashboardUserBackend",
    "django.contrib.auth.backends.ModelBackend",
)

REST_FRAMEWORK = {
    # Browser sessions are the only way in; there is no mobile or B2B client, so
    # DLA's PlatformAuthentication (bearer tokens) is not wired up.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Closed by default. The two public endpoints (health, me) opt out with an
    # explicit @permission_classes([AllowAny]).
    "DEFAULT_PERMISSION_CLASSES": ["deployments.permissions.IsTeamLead"],
    # DRF's default list also includes BrowsableAPIRenderer, which needs a
    # TEMPLATES setting this project has never had. The SPA is the only
    # consumer, so JSON-only keeps that true.
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

# DLA settings. CLIENT_ID/CLIENT_SECRET/REDIRECT_URI default to the LABS_CLIENT_ID,
# LABS_CLIENT_SECRET and LABS_REDIRECT_URI environment variables, and PLATFORM_URL
# defaults to https://platform.pennlabs.org -- so production needs no overrides
# here beyond what's in production.py.
#
# ADMIN_PERMISSION is DLA's built-in single-permission admin gate. Our own
# backend decides lead status from *any* `*_admin` codename, so this value is
# mostly moot -- but naming it something real (rather than DLA's `example_admin`
# default) means creating a `dashboard-leads` GitHub team would Just Work.
PLATFORM_ACCOUNTS = {
    "ADMIN_PERMISSION": "dashboard_admin",
    # Leave Django's admin site alone; we don't install one.
    "CUSTOM_ADMIN": False,
}

# Pennkeys that always have access, on top of the team-lead rule above.
#
# Lead status is derived from permissions team-sync pushes to Platform, and that
# pipeline only issues `*_admin` codenames to people who are BOTH a member of a
# GitHub `<product>-leads` team AND listed in team-sync's roster.yaml. Anyone who
# maintains this dashboard without leading a product team therefore has no
# `*_admin` codename and would be locked out of the tool they operate.
#
# This is also the escape hatch for a Platform lead: Platform's own
# ProductAdminView special-cases `platform_admin` and sets is_superuser instead
# of materializing a Permission, so `platform_admin` never comes back from
# introspection and the `*_admin` test cannot see it.
#
# Comma-separated env var so the list can change without a code deploy.
# Matching is case-insensitive; team-sync lowercases pennkeys.
DASHBOARD_ALLOWED_USERS = [
    pennkey.strip().lower()
    for pennkey in os.getenv("DASHBOARD_ALLOWED_USERS", "chenstan").split(",")
    if pennkey.strip()
]

# Optional. Authenticates the GitHub lookups behind commit messages and authors,
# which is what makes private repos visible and raises the rate limit from 60 to
# 5,000 requests an hour. Without it the dashboard still works; commits GitHub
# won't describe just show as bare SHAs. Needs read access to repo contents only.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# The Performance Insights data behind the Database page. Every product shares
# this one RDS instance. The resource id is its DbiResourceId, not its name, and
# the backend's IAM role (terraform/dashboard.tf in pennlabs/infrastructure) only
# has access to this one. Locally, boto3 uses your own AWS profile instead:
# `AWS_PROFILE=pennlabs ./dev.sh`.
PERFORMANCE_INSIGHTS_REGION = "us-east-1"
PERFORMANCE_INSIGHTS_RESOURCE_ID = os.getenv(
    "PERFORMANCE_INSIGHTS_RESOURCE_ID", "db-UZ6WEKHZ2ZTWOOJCPYO3KAQECM"
)
# Load above this many active sessions means queries are queueing for CPU. Drawn
# as a line on the graph, so update it if the instance is resized. db.t3.large.
DATABASE_VCPUS = int(os.getenv("DATABASE_VCPUS", "2"))

LOGIN_URL = "/api/accounts/login/"

# Sessions expire daily-ish so that a lead who rotates off the team loses access
# without needing to explicitly log out. `post_authenticate` re-checks their
# Platform permissions on every login.
SESSION_COOKIE_AGE = 12 * 60 * 60
# Required: Platform redirects back to our callback as a top-level cross-site
# GET, and the session cookie holding the OAuth `state` has to survive it.
SESSION_COOKIE_SAMESITE = "Lax"
