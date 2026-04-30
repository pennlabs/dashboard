"""HTTP views for the dashboard.

Every endpoint reads live from the Kubernetes API; nothing is persisted. This
module is intentionally thin -- the heavy lifting (label filtering, owner
reference walking, dict shaping) lives in `k8s_client`.
"""

from collections import defaultdict
from typing import Any

from django.http import JsonResponse
from kubernetes.client.exceptions import ApiException
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import k8s_client


def _build_products(deployments: list[Any]) -> dict[str, dict]:
    """Group a list of V1Deployments by their `app.kubernetes.io/part-of` label."""
    by_product: dict[str, list[dict]] = defaultdict(list)
    for dep in deployments:
        by_product[k8s_client.product_name(dep)].append(
            k8s_client.deployment_to_dict(dep)
        )

    result: dict[str, dict] = {}
    for name, dep_dicts in by_product.items():
        # A product is healthy iff every one of its deployments is healthy.
        is_healthy = bool(dep_dicts) and all(d["is_healthy"] for d in dep_dicts)
        result[name] = {
            "name": name,
            "display_name": name,
            "repo_url": f"https://github.com/pennlabs/{name}",
            "is_healthy": is_healthy,
            "deployments": dep_dicts,
        }
    return result


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(_request):
    """Liveness probe -- intentionally does not call the K8s API."""
    return JsonResponse({"status": "ok"})


@api_view(["GET"])
def list_products(_request):
    """All Penn Labs products derived from labels on live Deployments."""
    deployments = k8s_client.list_deployments()
    products = _build_products(deployments)
    return Response(sorted(products.values(), key=lambda p: p["name"]))


@api_view(["GET"])
def product_detail(_request, name: str):
    deployments = [
        d for d in k8s_client.list_deployments() if k8s_client.product_name(d) == name
    ]
    if not deployments:
        return Response({"error": f"product {name!r} not found"}, status=404)
    products = _build_products(deployments)
    return Response(products[name])


@api_view(["GET"])
def deployment_detail(_request, namespace: str, name: str):
    try:
        dep = k8s_client.get_deployment(namespace, name)
    except ApiException as exc:
        # 404 from the API server bubbles up as ApiException(status=404).
        return Response({"error": str(exc)}, status=exc.status or 500)

    payload = k8s_client.deployment_to_dict(dep)
    payload["replicasets"] = [
        k8s_client.replicaset_to_dict(rs)
        for rs in k8s_client.get_replicasets(namespace, name)
    ]
    return Response(payload)


@api_view(["GET"])
def deployment_pods(_request, namespace: str, name: str):
    pods = k8s_client.get_pods(namespace, name)
    return Response([k8s_client.pod_to_dict(p) for p in pods])


@api_view(["POST"])
def rollback_deployment(request, namespace: str, name: str):
    """Patch the deployment's container image to a previous revision.

    For a real production deployment we would gate this with admin auth; for
    the local demo it's open. The `image` field in the request body is
    typically copied from one of the older entries in `replicasets`.
    """
    image = request.data.get("image")
    if not image:
        return Response({"error": "image is required"}, status=400)
    try:
        k8s_client.rollback_deployment(namespace, name, image)
    except ApiException as exc:
        return Response({"error": str(exc)}, status=exc.status or 500)
    return Response({"status": "rollback triggered", "image": image})
