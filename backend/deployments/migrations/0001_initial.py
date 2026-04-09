from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Product",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100, unique=True)),
                ("display_name", models.CharField(max_length=200)),
                ("repo_url", models.URLField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name="Deployment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("namespace", models.CharField(max_length=100)),
                ("current_version", models.CharField(blank=True, max_length=40)),
                ("desired_replicas", models.IntegerField(default=0)),
                ("ready_replicas", models.IntegerField(default=0)),
                ("available_replicas", models.IntegerField(default=0)),
                ("updated_replicas", models.IntegerField(default=0)),
                ("is_healthy", models.BooleanField(default=False)),
                ("last_synced", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deployments",
                        to="deployments.product",
                    ),
                ),
            ],
            options={"unique_together": {("name", "namespace")}},
        ),
        migrations.CreateModel(
            name="DeploymentEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("version", models.CharField(max_length=40)),
                ("previous_version", models.CharField(blank=True, max_length=40)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("deploy", "Deploy"),
                            ("rollback", "Rollback"),
                            ("scale", "Scale"),
                        ],
                        max_length=20,
                    ),
                ),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("triggered_by", models.CharField(default="sync", max_length=100)),
                (
                    "deployment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="deployments.deployment",
                    ),
                ),
            ],
            options={"ordering": ["-timestamp"]},
        ),
        migrations.CreateModel(
            name="ReplicaSetSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("version", models.CharField(max_length=40)),
                ("image", models.CharField(max_length=500)),
                ("revision", models.IntegerField()),
                ("created_at", models.DateTimeField()),
                (
                    "deployment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="replicasets",
                        to="deployments.deployment",
                    ),
                ),
            ],
            options={
                "ordering": ["-revision"],
                "unique_together": {("deployment", "revision")},
            },
        ),
    ]
