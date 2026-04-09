import logging
import time

from django.core.management.base import BaseCommand

from deployments import k8s_client
from deployments.models import Deployment, DeploymentEvent, Product, ReplicaSetSnapshot

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Continuously syncs Kubernetes state to the database every 30 seconds"

    def handle(self, *args, **options):
        self.stdout.write("Starting sync worker...")
        while True:
            try:
                self._sync()
            except Exception as e:
                logger.error(f"Sync error: {e}", exc_info=True)
            time.sleep(30)

    def _sync(self):
        k8s_deps = k8s_client.list_deployments()
        self.stdout.write(f"Syncing {len(k8s_deps)} deployments")

        for k8s_dep in k8s_deps:
            product_name = k8s_client.extract_product_name(k8s_dep)
            new_version = k8s_client.extract_version(k8s_dep)

            product, _ = Product.objects.get_or_create(
                name=product_name,
                defaults={
                    "display_name": product_name.replace("-", " ").title(),
                    "repo_url": f"https://github.com/pennlabs/{product_name}",
                },
            )

            dep, created = Deployment.objects.get_or_create(
                name=k8s_dep.metadata.name,
                namespace=k8s_dep.metadata.namespace,
                defaults={"product": product},
            )

            old_version = dep.current_version

            if (created and new_version) or (
                not created
                and old_version
                and old_version != new_version
                and new_version
            ):
                DeploymentEvent.objects.create(
                    deployment=dep,
                    version=new_version,
                    previous_version=old_version if not created else "",
                    event_type=DeploymentEvent.DEPLOY,
                )

            dep.product = product
            dep.current_version = new_version
            dep.desired_replicas = k8s_dep.spec.replicas or 0
            dep.ready_replicas = k8s_dep.status.ready_replicas or 0
            dep.available_replicas = k8s_dep.status.available_replicas or 0
            dep.updated_replicas = k8s_dep.status.updated_replicas or 0
            dep.is_healthy = k8s_client.is_deployment_healthy(k8s_dep)
            dep.save()

            for rs in k8s_client.get_replicasets(dep.namespace, dep.name):
                revision_str = (rs.metadata.annotations or {}).get(
                    "deployment.kubernetes.io/revision"
                )
                if not revision_str:
                    continue
                revision = int(revision_str)
                containers = rs.spec.template.spec.containers or []
                image = containers[0].image if containers else ""
                ReplicaSetSnapshot.objects.update_or_create(
                    deployment=dep,
                    revision=revision,
                    defaults={
                        "version": k8s_client.extract_version_from_rs(rs),
                        "image": image,
                        "created_at": rs.metadata.creation_timestamp,
                    },
                )
