from rest_framework import serializers

from .models import Deployment, DeploymentEvent, Product, ReplicaSetSnapshot


class DeploymentEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeploymentEvent
        fields = [
            "id",
            "version",
            "previous_version",
            "event_type",
            "timestamp",
            "triggered_by",
        ]


class ReplicaSetSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReplicaSetSnapshot
        fields = ["id", "version", "image", "revision", "created_at"]


class DeploymentSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Deployment
        fields = [
            "id",
            "name",
            "namespace",
            "current_version",
            "desired_replicas",
            "ready_replicas",
            "is_healthy",
            "last_synced",
        ]


class DeploymentSerializer(serializers.ModelSerializer):
    events = DeploymentEventSerializer(many=True, read_only=True)
    replicasets = ReplicaSetSnapshotSerializer(many=True, read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = Deployment
        fields = [
            "id",
            "name",
            "namespace",
            "product_name",
            "current_version",
            "desired_replicas",
            "ready_replicas",
            "available_replicas",
            "updated_replicas",
            "is_healthy",
            "last_synced",
            "events",
            "replicasets",
        ]


class ProductSerializer(serializers.ModelSerializer):
    deployments = DeploymentSummarySerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "display_name",
            "repo_url",
            "is_healthy",
            "deployments",
        ]
