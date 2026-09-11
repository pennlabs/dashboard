from django.urls import include, path

urlpatterns = [
    path("api/", include("deployments.urls")),
    # OAuth: /api/accounts/login/, /callback/, /logout/.
    #
    # Our own urlconf rather than `accounts.urls`, so login and callback use the
    # hardened views in `deployments.oauth` -- DLA's versions turn a missing
    # session, a replayed code or an unreachable Platform into a blank HTTP 500,
    # and accept `next=//evil.com` as an open redirect. Same paths, same
    # `accounts` namespace.
    #
    # Mounted under /api/ for two reasons: the production ingress already routes
    # /api to this service (see k8s/main.ts), so no ingress change is needed;
    # and /api/accounts/callback/ is the exact path Penn Labs' shared
    # development OAuth client is registered against on platform-dev.
    path("api/accounts/", include("deployments.oauth_urls", namespace="accounts")),
]
