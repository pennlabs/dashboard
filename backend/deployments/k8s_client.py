"""Thin wrapper around the official Kubernetes Python client.

Every function here is a synchronous call to the live Kubernetes API server
(no caching, no database). The dashboard's API views call into this module on
every HTTP request, which gives us a real-time view at the cost of one round
trip to the cluster per page render.

All list calls are filtered by the `app.kubernetes.io/managed-by=kittyhawk`
label so the dashboard only shows resources Penn Labs actually manages, not
random system pods (kube-proxy, coredns, etc.).
"""

import logging
from typing import Any

from django.conf import settings
from kubernetes import client, config

logger = logging.getLogger(__name__)

# Penn Labs convention: every Kittyhawk-managed resource carries these labels.
# We filter on `managed-by` to scope the dashboard, and use `part-of` to group
# Deployments into "products" (e.g. penn-clubs has a frontend + backend + worker).
MANAGED_BY_LABEL = "app.kubernetes.io/managed-by=kittyhawk"
PART_OF_LABEL = "app.kubernetes.io/part-of"
VERSION_LABEL = "app.kubernetes.io/version"
NAME_LABEL = "app.kubernetes.io/name"


_config_loaded = False


def _load_config() -> None:
    """Load kubeconfig once per process.

    Honors the K8S_IN_CLUSTER setting:
      - True  -> read the ServiceAccount token mounted into the pod (in-cluster)
      - False -> read ~/.kube/config (local dev)
    """
    global _config_loaded
    if _config_loaded:
        return
    if getattr(settings, "K8S_IN_CLUSTER", False):
        config.load_incluster_config()
    else:
        config.load_kube_config()
    _config_loaded = True


def _apps() -> client.AppsV1Api:
    _load_config()
    return client.AppsV1Api()


def _core() -> client.CoreV1Api:
    _load_config()
    return client.CoreV1Api()


# ---------------------------------------------------------------------------
# Label extractors
# ---------------------------------------------------------------------------

def _label(obj: Any, key: str, default: str = "") -> str:
    return (obj.metadata.labels or {}).get(key, default)


def product_name(obj: Any) -> str:
    """Best-effort product name. Falls back to the deployment name if unlabeled."""
    return _label(obj, PART_OF_LABEL) or obj.metadata.name


def version(obj: Any) -> str:
    return _label(obj, VERSION_LABEL)


# ---------------------------------------------------------------------------
# Deployments
# ---------------------------------------------------------------------------

def list_deployments() -> list[Any]:
    """All Kittyhawk-managed Deployments across every namespace."""
    return _apps().list_deployment_for_all_namespaces(
        label_selector=MANAGED_BY_LABEL
    ).items


def get_deployment(namespace: str, name: str) -> Any:
    return _apps().read_namespaced_deployment(name=name, namespace=namespace)


def deployment_to_dict(dep: Any) -> dict[str, Any]:
    """Flatten a V1Deployment into the JSON shape the frontend expects."""
    spec = dep.spec or client.V1DeploymentSpec(replicas=0, selector=None, template=None)
    status = dep.status or client.V1DeploymentStatus()

    desired = spec.replicas or 0
    ready = status.ready_replicas or 0
    available = status.available_replicas or 0
    updated = status.updated_replicas or 0

    return {
        "name": dep.metadata.name,
        "namespace": dep.metadata.namespace,
        "product_name": product_name(dep),
        "current_version": version(dep),
        "desired_replicas": desired,
        "ready_replicas": ready,
        "available_replicas": available,
        "updated_replicas": updated,
        "is_healthy": desired > 0 and ready >= desired,
    }


# ---------------------------------------------------------------------------
# ReplicaSets (used to show rollout history + populate the rollback dialog)
# ---------------------------------------------------------------------------

def get_replicasets(namespace: str, deployment_name: str) -> list[Any]:
    """ReplicaSets owned by a given Deployment.

    A Deployment doesn't directly link its history; you have to look at every
    ReplicaSet in the namespace and find ones whose `ownerReferences` point at
    the Deployment. Newer ReplicaSets have higher `revision` annotations.
    """
    all_rs = _apps().list_namespaced_replica_set(
        namespace, label_selector=MANAGED_BY_LABEL
    ).items
    owned = []
    for rs in all_rs:
        for ref in rs.metadata.owner_references or []:
            if ref.kind == "Deployment" and ref.name == deployment_name:
                owned.append(rs)
                break
    # Sort newest first using the revision annotation Kubernetes maintains.
    owned.sort(
        key=lambda rs: int(
            (rs.metadata.annotations or {}).get(
                "deployment.kubernetes.io/revision", "0"
            )
        ),
        reverse=True,
    )
    return owned


def replicaset_to_dict(rs: Any) -> dict[str, Any]:
    revision = int(
        (rs.metadata.annotations or {}).get(
            "deployment.kubernetes.io/revision", "0"
        )
    )
    containers = (rs.spec.template.spec.containers or []) if rs.spec and rs.spec.template else []
    image = containers[0].image if containers else ""
    return {
        "revision": revision,
        "version": version(rs),
        "image": image,
        "created_at": (
            rs.metadata.creation_timestamp.isoformat()
            if rs.metadata.creation_timestamp
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Pods
# ---------------------------------------------------------------------------

def get_pods(namespace: str, deployment_name: str) -> list[Any]:
    """Pods belonging to a Deployment, matched by the `app.kubernetes.io/name` label.

    Penn Labs sets this label to the deployment's name, so we can find pods
    without walking through ReplicaSets.
    """
    return _core().list_namespaced_pod(
        namespace,
        label_selector=f"{NAME_LABEL}={deployment_name}",
    ).items


def pod_to_dict(pod: Any) -> dict[str, Any]:
    containers = []
    for cs in pod.status.container_statuses or []:
        # `state` is a oneof: running / waiting / terminated. We surface the
        # `waiting` reason because that's where errors like ImagePullBackOff
        # and CrashLoopBackOff live -- the most useful debugging signal.
        reason = None
        if cs.state and cs.state.waiting:
            reason = cs.state.waiting.reason
        containers.append(
            {
                "name": cs.name,
                "ready": bool(cs.ready),
                "restart_count": cs.restart_count or 0,
                "reason": reason,
            }
        )
    return {
        "name": pod.metadata.name,
        "phase": pod.status.phase,
        "start_time": (
            pod.status.start_time.isoformat() if pod.status.start_time else None
        ),
        "containers": containers,
    }


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

def rollback_deployment(namespace: str, name: str, image: str) -> None:
    """Patch the Deployment's first container image.

    Patching the spec is exactly what `kubectl set image` does. The Deployment
    controller then creates a new ReplicaSet matching the new spec and scales
    down the old one -- the standard rolling update mechanism.
    """
    apps = _apps()
    deployment = apps.read_namespaced_deployment(name=name, namespace=namespace)
    container_name = deployment.spec.template.spec.containers[0].name
    patch = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [{"name": container_name, "image": image}]
                }
            }
        }
    }
    apps.patch_namespaced_deployment(name=name, namespace=namespace, body=patch)
