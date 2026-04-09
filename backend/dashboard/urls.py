from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("deployments.urls")),
    path("accounts/", include("accounts.urls")),
    path("api-auth/", include("rest_framework.urls")),
]
