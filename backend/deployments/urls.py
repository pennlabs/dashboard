from django.urls import path

from . import views

urlpatterns = [
    path("products/", views.ProductListView.as_view()),
    path("products/<str:name>/", views.ProductDetailView.as_view()),
    path("deployments/<int:pk>/", views.DeploymentDetailView.as_view()),
    path("deployments/<int:pk>/pods/", views.deployment_pods),
    path("deployments/<int:pk>/rollback/", views.rollback_deployment),
    path("health/", views.health_check),
]
