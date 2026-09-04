from django.urls import include, path

urlpatterns = [
    path("api/", include("deployments.urls")),
    # django-labs-accounts: /api/accounts/login/, /callback/, /logout/.
    #
    # Mounted under /api/ for two reasons: the production ingress already routes
    # /api to this service (see k8s/main.ts), so no ingress change is needed;
    # and /api/accounts/callback/ is the exact path Penn Labs' shared
    # development OAuth client is registered against on platform-dev.
    path("api/accounts/", include("accounts.urls", namespace="accounts")),
]
