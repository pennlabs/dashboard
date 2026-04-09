import logging

from django.conf import settings
from kubernetes import client, config

logger = logging.getLogger(__name__)

_config_loaded = False


def _load_config():
    global _config_loaded
    if _config_loaded:
        return
    if getattr(settings, "K8S_IN_CLUSTER", False):
        config.load_incluster_config()
    else:
        config.load_kube_config()
    _config_loaded = True


def list_deployments():
    _load_config()
    v1 = client.AppsV1Api()
    result = v1.list_deployment_for_all_namespaces(
        label_selector="app.kubernetes.io/managed-by=kittyhawk"
    )
    return result.items


def get_replicasets(namespace, deployment_name):
    _load_config()
    v1 = client.AppsV1Api()
    all_rs = v1.list_namespaced_replica_set(
        namespace,
        label_selector="app.kubernetes.io/managed-by=kittyhawk",
    ).items
    owned = []
    for rs in all_rs:
        for ref in rs.metadata.owner_references or []:
            if ref.kind == "Deployment" and ref.name == deployment_name:
                owned.append(rs)
    return owned


def get_pods(namespace, deployment_name):
    _load_config()
    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(
        namespace,
        label_selector=f"app.kubernetes.io/name={deployment_name}",
    )
    return pods.items


def rollback_deployment(name, namespace, image):
    _load_config()
    v1 = client.AppsV1Api()
    # Read the live deployment to get the real container name
    deployment = v1.read_namespaced_deployment(name=name, namespace=namespace)
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
    v1.patch_namespaced_deployment(name=name, namespace=namespace, body=patch)


def extract_product_name(deployment):
    labels = deployment.metadata.labels or {}
    return labels.get("app.kubernetes.io/part-of", deployment.metadata.name)


def extract_version(deployment):
    labels = deployment.metadata.labels or {}
    return labels.get("app.kubernetes.io/version", "")


def extract_version_from_rs(rs):
    labels = rs.metadata.labels or {}
    return labels.get("app.kubernetes.io/version", "")


def is_deployment_healthy(deployment):
    desired = deployment.spec.replicas or 0
    ready = deployment.status.ready_replicas or 0
    return desired > 0 and ready >= desired
