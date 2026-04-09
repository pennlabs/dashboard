from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=200)
    repo_url = models.URLField(blank=True)

    @property
    def is_healthy(self) -> bool:
        deployments = self.deployments.all()
        if not deployments.exists():
            return False
        return all(dep.is_healthy for dep in deployments)

    def __str__(self) -> str:
        return self.display_name


class Deployment(models.Model):
    product = models.ForeignKey(
        Product, related_name="deployments", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=200)
    namespace = models.CharField(max_length=100)
    current_version = models.CharField(max_length=40, blank=True)
    desired_replicas = models.IntegerField(default=0)
    ready_replicas = models.IntegerField(default=0)
    available_replicas = models.IntegerField(default=0)
    updated_replicas = models.IntegerField(default=0)
    is_healthy = models.BooleanField(default=False)
    last_synced = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("name", "namespace")

    def __str__(self) -> str:
        return f"{self.name}.{self.namespace}"


class DeploymentEvent(models.Model):
    DEPLOY = "deploy"
    ROLLBACK = "rollback"
    SCALE = "scale"
    EVENT_TYPE_CHOICES = [
        (DEPLOY, "Deploy"),
        (ROLLBACK, "Rollback"),
        (SCALE, "Scale"),
    ]

    deployment = models.ForeignKey(
        Deployment, related_name="events", on_delete=models.CASCADE
    )
    version = models.CharField(max_length=40, blank=True)
    previous_version = models.CharField(max_length=40, blank=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    triggered_by = models.CharField(max_length=100, default="sync")

    class Meta:
        ordering = ["-timestamp"]


class ReplicaSetSnapshot(models.Model):
    deployment = models.ForeignKey(
        Deployment, related_name="replicasets", on_delete=models.CASCADE
    )
    version = models.CharField(max_length=40)
    image = models.CharField(max_length=500)
    revision = models.IntegerField()
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["-revision"]
        unique_together = ("deployment", "revision")
