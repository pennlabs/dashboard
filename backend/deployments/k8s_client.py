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
import re
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


def image_tag(image: str) -> str:
    """The tag portion of a container image reference, or "" if untagged.

    Kittyhawk tags every image with the deploying commit
    (`pennlabs/penn-clubs-backend:c196b603...`), so for anything it manages the
    tag *is* the git SHA. This is the only place a ReplicaSet's version can be
    recovered from -- see `replicaset_to_dict`.

    Splits on the last colon, but only after the last slash, so that a registry
    host with a port (`registry:5000/img`) isn't mistaken for a tag.
    """
    repo, _, tag = image.rpartition(":")
    if not repo or "/" in tag:
        return ""
    return tag


def image_repository(image: str) -> str:
    """Everything before the tag, e.g. `pennlabs/penn-clubs-backend`."""
    tag = image_tag(image)
    return image[: -(len(tag) + 1)] if tag else image


_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def looks_like_commit(tag: str) -> bool:
    """Is this image tag plausibly a git commit SHA?

    Only Kittyhawk-built product images are tagged with a commit. Plenty of
    Deployments in the cluster run upstream images instead -- the per-product
    Redis sidecars are tagged `6.0` and `6.2.6-v6`, for instance -- and those
    Deployments still carry a real commit in their version label, because the
    label describes the *release* that deployed them.

    So a tag is only usable as a version when it looks like a SHA. Without this
    check we would show `6.0` as a Redis Deployment's version (and link to
    github.com/pennlabs/<product>/commit/6.0, a 404), and a rollback would
    overwrite a perfectly good commit label with `6.0`.
    """
    return bool(_SHA_RE.match(tag))


def _commit_from_image(image: str) -> str:
    """The commit SHA an image was built from, or "" if its tag isn't one."""
    tag = image_tag(image)
    return tag if looks_like_commit(tag) else ""


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
    """ReplicaSets owned by a given Deployment, newest revision first.

    A Deployment doesn't directly link its history; you have to look at the
    ReplicaSets in the namespace and find ones whose `ownerReferences` point at
    the Deployment. Newer ReplicaSets have higher `revision` annotations.

    NOTE on the selector: we filter on `app.kubernetes.io/name`, NOT on
    `managed-by=kittyhawk` like the Deployment listing does. A ReplicaSet
    inherits its labels from the Deployment's *pod template*, not from the
    Deployment's own metadata -- and Kittyhawk only puts
    `app.kubernetes.io/name` on the pod template. Selecting on `managed-by`
    here matches literally zero ReplicaSets in the real cluster, which silently
    emptied the rollout history and made the rollback UI unreachable.
    """
    all_rs = _apps().list_namespaced_replica_set(
        namespace, label_selector=f"{NAME_LABEL}={deployment_name}"
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
        # Fall back to the image tag: Kittyhawk keeps the version label on the
        # Deployment, not the pod template, so a ReplicaSet almost never carries
        # one and this field was always "" (rendering every history row as "—").
        # For product images the tag is the deploying commit. For upstream images
        # (a Redis sidecar tagged `6.0`) it isn't a version at all, so leave it
        # blank rather than render a link to a commit that doesn't exist.
        "version": version(rs) or _commit_from_image(image),
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

class InvalidRollbackTarget(ValueError):
    """The requested image is not a previous revision of this Deployment."""


def rollback_deployment(namespace: str, name: str, image: str) -> None:
    """Roll a Deployment back to a previously-deployed image.

    Patching the pod template is exactly what `kubectl set image` does: the
    Deployment controller then creates a new ReplicaSet matching the new spec
    and scales down the old one -- the standard rolling update mechanism.

    Two things this deliberately does beyond swapping the image:

    1. It refuses any image that isn't already in this Deployment's own
       ReplicaSet history. Without that check the endpoint accepts an arbitrary
       string and patches it straight into the cluster, so any authorized user
       could run any image in any namespace -- and the ClusterRole grants
       `patch` on deployments cluster-wide. "Roll back" should mean going back
       to something that actually ran here before, and the UI only ever offers
       exactly those images.
    2. It updates the `app.kubernetes.io/version` label to match. The dashboard
       reads the *label* for "current version", so patching only the image left
       the UI reporting the pre-rollback SHA while running the older code --
       i.e. the rollback looked like it had done nothing.

    Raises:
        InvalidRollbackTarget: if `image` was never deployed here.
    """
    apps = _apps()

    # Validate against history first, so a bad request never reaches the cluster.
    history = get_replicasets(namespace, name)
    known_images = {
        rs.spec.template.spec.containers[0].image
        for rs in history
        if rs.spec and rs.spec.template and rs.spec.template.spec.containers
    }
    if image not in known_images:
        raise InvalidRollbackTarget(
            f"{image!r} is not a previous revision of {namespace}/{name}"
        )

    deployment = apps.read_namespaced_deployment(name=name, namespace=namespace)
    containers = deployment.spec.template.spec.containers or []
    if not containers:
        raise InvalidRollbackTarget(f"{namespace}/{name} has no containers to patch")

    # With one container (every Kittyhawk app) there's no ambiguity. With a
    # sidecar, pick the container already running the same image repository
    # rather than blindly taking the first one, which could point a sidecar at
    # the app's image.
    if len(containers) == 1:
        target = containers[0]
    else:
        repo = image_repository(image)
        matches = [c for c in containers if image_repository(c.image) == repo]
        if len(matches) != 1:
            raise InvalidRollbackTarget(
                f"cannot tell which container of {namespace}/{name} to roll back "
                f"to {image!r}"
            )
        target = matches[0]

    patch: dict[str, Any] = {
        "spec": {
            "template": {
                "spec": {"containers": [{"name": target.name, "image": image}]}
            }
        }
    }

    # Keep the version label in step with the image actually running -- but only
    # when the tag is actually a commit. Deployments running upstream images (the
    # per-product Redis sidecars, tagged `6.0`) carry the *release's* commit in
    # this label, so clobbering it with `6.0` would lose real information and
    # point the UI's commit link at a SHA that doesn't exist. Leaving those
    # labels untouched is strictly better than corrupting them.
    commit = _commit_from_image(image)
    if commit:
        patch["metadata"] = {"labels": {VERSION_LABEL: commit}}

    apps.patch_namespaced_deployment(name=name, namespace=namespace, body=patch)
