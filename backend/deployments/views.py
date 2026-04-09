import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from . import k8s_client
from .models import Deployment, DeploymentEvent, Product
from .serializers import DeploymentSerializer, ProductSerializer

logger = logging.getLogger(__name__)


class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        return Product.objects.prefetch_related("deployments").all()


class ProductDetailView(generics.RetrieveAPIView):
    serializer_class = ProductSerializer

    def get_object(self):
        return get_object_or_404(
            Product.objects.prefetch_related("deployments"), name=self.kwargs["name"]
        )


class DeploymentDetailView(generics.RetrieveAPIView):
    serializer_class = DeploymentSerializer

    def get_queryset(self):
        return Deployment.objects.prefetch_related("events", "replicasets").all()


@api_view(["GET"])
def deployment_pods(request, pk):
    dep = get_object_or_404(Deployment, pk=pk)
    pods = k8s_client.get_pods(dep.namespace, dep.name)
    data = []
    for pod in pods:
        containers = []
        for cs in pod.status.container_statuses or []:
            reason = None
            if cs.state and cs.state.waiting:
                reason = cs.state.waiting.reason
            containers.append(
                {
                    "name": cs.name,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                    "reason": reason,
                }
            )
        data.append(
            {
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "start_time": (
                    pod.status.start_time.isoformat() if pod.status.start_time else None
                ),
                "containers": containers,
            }
        )
    return Response(data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def rollback_deployment(request, pk):
    dep = get_object_or_404(Deployment, pk=pk)
    image = request.data.get("image")
    if not image:
        return Response({"error": "image is required"}, status=400)

    k8s_client.rollback_deployment(dep.name, dep.namespace, image)
    # image looks like "pennlabs/dashboard-backend:abc1234"
    target_version = image.split(":")[-1] if ":" in image else ""
    DeploymentEvent.objects.create(
        deployment=dep,
        version=target_version,
        previous_version=dep.current_version,
        event_type=DeploymentEvent.ROLLBACK,
        triggered_by=request.user.username,
    )
    return Response({"status": "rollback triggered"})


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return JsonResponse({"status": "ok"})
