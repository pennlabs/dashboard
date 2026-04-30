"""Unit tests for the dashboard API.

The Kubernetes client is mocked out entirely -- these tests verify our view
logic (label-based grouping, dict shaping, error handling) in isolation, with
no real cluster required. Run with:

    python manage.py test
"""

from types import SimpleNamespace
from unittest import mock

from django.test import Client, SimpleTestCase
from kubernetes.client.exceptions import ApiException


# We use SimpleTestCase (not TestCase) because there is no database to set up
# or tear down -- the dashboard reads live from the Kubernetes API.


def _fake_deployment(name, namespace, product, version, replicas=2, ready=2):
    """Build a fake V1Deployment-shaped object using SimpleNamespace.

    Only the attributes our code actually reads need to be present.
    """
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            namespace=namespace,
            labels={
                "app.kubernetes.io/managed-by": "kittyhawk",
                "app.kubernetes.io/part-of": product,
                "app.kubernetes.io/version": version,
                "app.kubernetes.io/name": name,
            },
            annotations={},
            owner_references=[],
        ),
        spec=SimpleNamespace(replicas=replicas),
        status=SimpleNamespace(
            ready_replicas=ready,
            available_replicas=ready,
            updated_replicas=ready,
        ),
    )


class ProductsApiTest(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @mock.patch("deployments.k8s_client.list_deployments")
    def test_products_groups_by_part_of_label(self, mock_list):
        mock_list.return_value = [
            _fake_deployment("clubs-backend", "default", "penn-clubs", "abc123"),
            _fake_deployment("clubs-frontend", "default", "penn-clubs", "abc123"),
            _fake_deployment("ohq-backend", "default", "ohq", "def456"),
        ]

        response = self.client.get("/api/products/")

        self.assertEqual(response.status_code, 200)
        products = response.json()
        self.assertEqual(len(products), 2)
        names = [p["name"] for p in products]
        self.assertEqual(names, ["ohq", "penn-clubs"])  # sorted alphabetically

        clubs = next(p for p in products if p["name"] == "penn-clubs")
        self.assertEqual(len(clubs["deployments"]), 2)
        self.assertTrue(clubs["is_healthy"])

    @mock.patch("deployments.k8s_client.list_deployments")
    def test_product_is_unhealthy_if_any_deployment_unhealthy(self, mock_list):
        mock_list.return_value = [
            _fake_deployment("clubs-backend", "default", "penn-clubs", "abc", ready=2),
            _fake_deployment("clubs-frontend", "default", "penn-clubs", "abc", ready=0),
        ]

        response = self.client.get("/api/products/")

        clubs = response.json()[0]
        self.assertFalse(clubs["is_healthy"])

    @mock.patch("deployments.k8s_client.list_deployments")
    def test_product_detail_returns_404_for_unknown_product(self, mock_list):
        mock_list.return_value = []

        response = self.client.get("/api/products/nonexistent/")

        self.assertEqual(response.status_code, 404)


class DeploymentApiTest(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @mock.patch("deployments.k8s_client.get_replicasets")
    @mock.patch("deployments.k8s_client.get_deployment")
    def test_deployment_detail_includes_replicaset_history(self, mock_get, mock_rs):
        mock_get.return_value = _fake_deployment(
            "clubs-backend", "default", "penn-clubs", "abc"
        )
        mock_rs.return_value = [
            SimpleNamespace(
                metadata=SimpleNamespace(
                    name="rs-2",
                    annotations={"deployment.kubernetes.io/revision": "2"},
                    labels={"app.kubernetes.io/version": "abc123"},
                    creation_timestamp=None,
                ),
                spec=SimpleNamespace(
                    template=SimpleNamespace(
                        spec=SimpleNamespace(
                            containers=[SimpleNamespace(image="pennlabs/clubs:abc123")]
                        )
                    )
                ),
            ),
        ]

        response = self.client.get("/api/deployments/default/clubs-backend/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["name"], "clubs-backend")
        self.assertEqual(len(body["replicasets"]), 1)
        self.assertEqual(body["replicasets"][0]["revision"], 2)

    @mock.patch("deployments.k8s_client.get_deployment")
    def test_deployment_detail_404_when_k8s_404s(self, mock_get):
        mock_get.side_effect = ApiException(status=404, reason="Not Found")

        response = self.client.get("/api/deployments/default/missing/")

        self.assertEqual(response.status_code, 404)


class RollbackApiTest(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @mock.patch("deployments.k8s_client.rollback_deployment")
    def test_rollback_requires_image(self, mock_rollback):
        response = self.client.post(
            "/api/deployments/default/clubs-backend/rollback/",
            data={},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        mock_rollback.assert_not_called()

    @mock.patch("deployments.k8s_client.rollback_deployment")
    def test_rollback_calls_k8s_client_with_image(self, mock_rollback):
        response = self.client.post(
            "/api/deployments/default/clubs-backend/rollback/",
            data={"image": "pennlabs/clubs:abc123"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        mock_rollback.assert_called_once_with(
            "default", "clubs-backend", "pennlabs/clubs:abc123"
        )


class HealthCheckTest(SimpleTestCase):
    def test_health_check_returns_ok(self):
        response = Client().get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
