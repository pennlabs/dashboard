"""OAuth routes, replacing `accounts.urls` from django-labs-accounts.

Same paths and names as DLA's own urlconf -- the namespace stays `accounts` so
`reverse("accounts:login")`, `reverse("accounts:callback")` and `LOGIN_URL` keep
working, both for our code and DLA's internals. All three views point at the
hardened subclasses in `deployments.oauth`.

DLA's `token/` route is deliberately omitted: it exists for mobile clients doing
their own authorization-code exchange, and this dashboard is browser-only. Not
routing it means one less unauthenticated, CSRF-exempt endpoint exposed.
"""

from django.urls import path

from deployments.oauth import (
    DashboardCallbackView,
    DashboardLoginView,
    DashboardLogoutView,
)


app_name = "accounts"

urlpatterns = [
    path("login/", DashboardLoginView.as_view(), name="login"),
    path("callback/", DashboardCallbackView.as_view(), name="callback"),
    path("logout/", DashboardLogoutView.as_view(), name="logout"),
]
