from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health_check),
    path("me/", views.me),
    path("products/", views.list_products),
    path("products/<str:name>/", views.product_detail),
    path(
        "deployments/<str:namespace>/<str:name>/",
        views.deployment_detail,
    ),
    path(
        "deployments/<str:namespace>/<str:name>/pods/",
        views.deployment_pods,
    ),
    path(
        "deployments/<str:namespace>/<str:name>/rollback/",
        views.rollback_deployment,
    ),
]
