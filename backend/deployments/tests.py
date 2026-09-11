"""Unit tests for the dashboard API.

The Kubernetes client is mocked out entirely -- these tests verify our view
logic (label-based grouping, dict shaping, error handling) in isolation, with
no real cluster required. Run with:

    python manage.py test
"""

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from kubernetes.client.exceptions import ApiException

from deployments import k8s_client
from deployments.backends import DashboardUserBackend


User = get_user_model()

# TestCase (not SimpleTestCase) because authentication needs a database: users,
# sessions and permissions live there. Deployment data still never touches it --
# that is read live from the Kubernetes API and mocked out below.
#
# Every endpoint except /api/health/ and /api/me/ requires a signed-in team lead,
# which is recorded as `is_staff`. `_login_as_lead` is what most tests need.


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


def _make_user(username, is_lead):
    """Create a local user the way DLA does: no usable password, lead == is_staff."""
    user = User.objects.create(username=username, is_staff=is_lead, is_superuser=is_lead)
    user.set_unusable_password()
    user.save()
    return user


class LeadClientMixin:
    """Signs the test client in as a team lead.

    `force_login` skips the OAuth round-trip (that is exercised separately in
    DashboardUserBackendTest) and also bypasses CSRF, which is why these tests
    don't have to thread an X-CSRFToken header through every POST.
    """

    def setUp(self):
        self.client = Client()
        self.user = _make_user("tlead", is_lead=True)
        self.client.force_login(self.user)


class ProductsApiTest(LeadClientMixin, TestCase):
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


class DeploymentApiTest(LeadClientMixin, TestCase):
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


class RollbackApiTest(LeadClientMixin, TestCase):
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


class HealthCheckTest(TestCase):
    def test_health_check_returns_ok_without_logging_in(self):
        response = Client().get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class AccessControlTest(TestCase):
    """The dashboard is limited to team leads; prove it at the HTTP boundary."""

    @mock.patch("deployments.k8s_client.list_deployments", return_value=[])
    def test_anonymous_cannot_list_products(self, _mock_list):
        self.assertEqual(Client().get("/api/products/").status_code, 403)

    @mock.patch("deployments.k8s_client.list_deployments", return_value=[])
    def test_signed_in_non_lead_cannot_list_products(self, _mock_list):
        client = Client()
        client.force_login(_make_user("notalead", is_lead=False))
        self.assertEqual(client.get("/api/products/").status_code, 403)

    @mock.patch("deployments.k8s_client.list_deployments", return_value=[])
    def test_lead_can_list_products(self, _mock_list):
        client = Client()
        client.force_login(_make_user("alead", is_lead=True))
        self.assertEqual(client.get("/api/products/").status_code, 200)

    @mock.patch("deployments.k8s_client.rollback_deployment")
    def test_anonymous_cannot_roll_back(self, mock_rollback):
        response = Client().post(
            "/api/deployments/default/clubs-backend/rollback/",
            data={"image": "pennlabs/clubs:abc123"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        # The important half: we rejected the request before touching the cluster.
        mock_rollback.assert_not_called()

    @mock.patch("deployments.k8s_client.rollback_deployment")
    def test_signed_in_non_lead_cannot_roll_back(self, mock_rollback):
        client = Client()
        client.force_login(_make_user("notalead", is_lead=False))

        response = client.post(
            "/api/deployments/default/clubs-backend/rollback/",
            data={"image": "pennlabs/clubs:abc123"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        mock_rollback.assert_not_called()

    def test_me_reports_anonymous(self):
        response = Client().get("/api/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"authenticated": False, "is_lead": False, "user": None}
        )

    def test_me_reports_lead(self):
        client = Client()
        client.force_login(_make_user("alead", is_lead=True))

        body = client.get("/api/me/").json()

        self.assertTrue(body["authenticated"])
        self.assertTrue(body["is_lead"])
        self.assertEqual(body["user"]["pennkey"], "alead")

    def test_me_reports_signed_in_non_lead(self):
        client = Client()
        client.force_login(_make_user("notalead", is_lead=False))

        body = client.get("/api/me/").json()

        # Signed in, but the SPA should still show the "leads only" screen.
        self.assertTrue(body["authenticated"])
        self.assertFalse(body["is_lead"])

    def test_me_sets_csrf_cookie(self):
        # The SPA relies on this to obtain a token for the rollback POST.
        self.assertIn("csrftoken", Client().get("/api/me/").cookies)


class DashboardUserBackendTest(TestCase):
    """Mapping from Platform permissions to lead status.

    team-sync issues `<team>_admin` codenames only to members of GitHub `*-leads`
    teams and to Directors, so any one of them means "team lead". These tests
    drive `post_authenticate` directly rather than standing up an OAuth server.
    """

    def _post_authenticate(self, user, permissions):
        DashboardUserBackend().post_authenticate(
            user, created=False, dictionary={"user_permissions": permissions}
        )
        user.refresh_from_db()
        return user

    def test_single_product_admin_grants_access(self):
        user = self._post_authenticate(
            _make_user("clubslead", is_lead=False), ["penn_clubs_admin"]
        )
        self.assertTrue(user.is_staff)

    def test_director_with_every_admin_permission_grants_access(self):
        user = self._post_authenticate(
            _make_user("director", is_lead=False),
            ["penn_clubs_admin", "mobile_admin", "ohq_admin", "hub_admin"],
        )
        self.assertTrue(user.is_staff)

    def test_no_permissions_denies_access(self):
        user = self._post_authenticate(_make_user("member", is_lead=False), [])
        self.assertFalse(user.is_staff)

    def test_unrelated_permission_denies_access(self):
        user = self._post_authenticate(
            _make_user("member", is_lead=False), ["add_logentry", "view_user"]
        )
        self.assertFalse(user.is_staff)

    def test_former_lead_is_demoted(self):
        # A lead who rotated off the team loses access at their next login.
        user = self._post_authenticate(_make_user("exlead", is_lead=True), [])
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_legacy_product_permission_key_is_honored(self):
        user = _make_user("clubslead", is_lead=False)
        DashboardUserBackend().post_authenticate(
            user, created=False, dictionary={"product_permission": ["penn_clubs_admin"]}
        )
        user.refresh_from_db()
        self.assertTrue(user.is_staff)


def _fake_replicaset(revision, image, name="rs", deployment="clubs-backend", labels=None):
    """A ReplicaSet shaped like the real thing.

    Note the labels: a ReplicaSet inherits the Deployment's *pod template*
    labels, and Kittyhawk only puts `app.kubernetes.io/name` there. Fixtures
    that also add `managed-by` here do not reflect the real cluster.
    """
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            annotations={"deployment.kubernetes.io/revision": str(revision)},
            labels=labels if labels is not None else {"app.kubernetes.io/name": deployment},
            creation_timestamp=None,
            owner_references=[SimpleNamespace(kind="Deployment", name=deployment)],
        ),
        spec=SimpleNamespace(
            template=SimpleNamespace(
                spec=SimpleNamespace(containers=[SimpleNamespace(name="worker", image=image)])
            )
        ),
    )


def _fake_live_deployment(containers):
    return SimpleNamespace(
        metadata=SimpleNamespace(name="clubs-backend", namespace="default", labels={}),
        spec=SimpleNamespace(
            template=SimpleNamespace(spec=SimpleNamespace(containers=containers))
        ),
    )


class ImageTagTest(SimpleTestCase):
    """Kittyhawk tags images with the deploying commit, so tag == version."""

    def test_extracts_tag(self):
        self.assertEqual(k8s_client.image_tag("pennlabs/clubs:abc123"), "abc123")

    def test_untagged_image_has_no_tag(self):
        self.assertEqual(k8s_client.image_tag("pennlabs/clubs"), "")

    def test_registry_port_is_not_mistaken_for_a_tag(self):
        # The colon here belongs to the registry host, not a tag.
        self.assertEqual(k8s_client.image_tag("registry:5000/pennlabs/clubs"), "")

    def test_repository_strips_the_tag(self):
        self.assertEqual(
            k8s_client.image_repository("pennlabs/clubs:abc123"), "pennlabs/clubs"
        )

    def test_repository_of_untagged_image_is_itself(self):
        self.assertEqual(
            k8s_client.image_repository("pennlabs/clubs"), "pennlabs/clubs"
        )


class GetReplicaSetsTest(SimpleTestCase):
    """Regression tests for the selector that broke rollout history."""

    @mock.patch("deployments.k8s_client._apps")
    def test_selects_on_name_label_not_managed_by(self, mock_apps):
        # `managed-by` is on the Deployment, never on the pod template, so it
        # matches zero ReplicaSets in a real cluster. Selecting on it emptied
        # the history and made the rollback UI unreachable.
        mock_apps.return_value.list_namespaced_replica_set.return_value = (
            SimpleNamespace(items=[])
        )

        k8s_client.get_replicasets("default", "clubs-backend")

        _, kwargs = mock_apps.return_value.list_namespaced_replica_set.call_args
        self.assertEqual(
            kwargs["label_selector"], "app.kubernetes.io/name=clubs-backend"
        )
        self.assertNotIn("managed-by", kwargs["label_selector"])

    @mock.patch("deployments.k8s_client._apps")
    def test_finds_replicasets_with_realistic_labels(self, mock_apps):
        # Exactly the labels a real ReplicaSet carries -- no managed-by.
        rs = _fake_replicaset(
            2,
            "pennlabs/clubs:new",
            labels={
                "app.kubernetes.io/name": "clubs-backend",
                "pod-template-hash": "abc123",
            },
        )
        mock_apps.return_value.list_namespaced_replica_set.return_value = (
            SimpleNamespace(items=[rs])
        )

        found = k8s_client.get_replicasets("default", "clubs-backend")

        self.assertEqual(len(found), 1)

    @mock.patch("deployments.k8s_client._apps")
    def test_ignores_replicasets_owned_by_another_deployment(self, mock_apps):
        mine = _fake_replicaset(1, "pennlabs/clubs:a", name="mine")
        theirs = _fake_replicaset(1, "pennlabs/other:b", name="theirs", deployment="other")
        mock_apps.return_value.list_namespaced_replica_set.return_value = (
            SimpleNamespace(items=[mine, theirs])
        )

        found = k8s_client.get_replicasets("default", "clubs-backend")

        self.assertEqual([rs.metadata.name for rs in found], ["mine"])

    @mock.patch("deployments.k8s_client._apps")
    def test_sorted_newest_revision_first(self, mock_apps):
        mock_apps.return_value.list_namespaced_replica_set.return_value = (
            SimpleNamespace(
                items=[
                    _fake_replicaset(1, "pennlabs/clubs:old", name="old"),
                    _fake_replicaset(3, "pennlabs/clubs:new", name="new"),
                    _fake_replicaset(2, "pennlabs/clubs:mid", name="mid"),
                ]
            )
        )

        found = k8s_client.get_replicasets("default", "clubs-backend")

        self.assertEqual([rs.metadata.name for rs in found], ["new", "mid", "old"])


class ReplicaSetToDictTest(SimpleTestCase):
    def test_version_falls_back_to_image_tag(self):
        # No version label, which is the normal case in production.
        rs = _fake_replicaset(4, "pennlabs/clubs:c196b603")

        self.assertEqual(k8s_client.replicaset_to_dict(rs)["version"], "c196b603")

    def test_version_label_wins_when_present(self):
        rs = _fake_replicaset(
            4,
            "pennlabs/clubs:tagsha",
            labels={"app.kubernetes.io/version": "labelsha"},
        )

        self.assertEqual(k8s_client.replicaset_to_dict(rs)["version"], "labelsha")


class RollbackDeploymentTest(SimpleTestCase):
    """Tests the real rollback_deployment body, which had no coverage at all.

    Every other rollback test mocks this function out, so nothing exercised the
    patch it builds.
    """

    def setUp(self):
        self.history = [
            _fake_replicaset(3, "pennlabs/clubs:current", name="rs3"),
            _fake_replicaset(2, "pennlabs/clubs:previous", name="rs2"),
        ]

    def _run(self, image, containers=None, history=None):
        containers = containers or [SimpleNamespace(name="worker", image="pennlabs/clubs:current")]
        with mock.patch("deployments.k8s_client._apps") as mock_apps, mock.patch(
            "deployments.k8s_client.get_replicasets",
            return_value=self.history if history is None else history,
        ):
            mock_apps.return_value.read_namespaced_deployment.return_value = (
                _fake_live_deployment(containers)
            )
            k8s_client.rollback_deployment("default", "clubs-backend", image)
            return mock_apps.return_value.patch_namespaced_deployment

    def test_patches_the_container_image(self):
        patch = self._run("pennlabs/clubs:previous")

        body = patch.call_args.kwargs["body"]
        container = body["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["name"], "worker")
        self.assertEqual(container["image"], "pennlabs/clubs:previous")

    def test_also_updates_the_version_label(self):
        # The dashboard reads current_version from this label. Patching only the
        # image left the UI showing the pre-rollback SHA -- the rollback looked
        # like a no-op even though the older image was running.
        patch = self._run("pennlabs/clubs:previous")

        body = patch.call_args.kwargs["body"]
        self.assertEqual(
            body["metadata"]["labels"]["app.kubernetes.io/version"], "previous"
        )

    def test_no_version_label_written_for_untagged_image(self):
        history = [_fake_replicaset(2, "pennlabs/clubs", name="rs2")]

        patch = self._run("pennlabs/clubs", history=history)

        self.assertNotIn("metadata", patch.call_args.kwargs["body"])

    def test_rejects_image_not_in_history(self):
        # The security-relevant case: an arbitrary image must never be patched
        # into the cluster, since the ClusterRole allows patching any Deployment.
        with self.assertRaises(k8s_client.InvalidRollbackTarget):
            self._run("attacker/evil:latest")

    def test_rejects_image_without_touching_the_cluster(self):
        with mock.patch("deployments.k8s_client._apps") as mock_apps, mock.patch(
            "deployments.k8s_client.get_replicasets", return_value=self.history
        ):
            with self.assertRaises(k8s_client.InvalidRollbackTarget):
                k8s_client.rollback_deployment(
                    "default", "clubs-backend", "attacker/evil:latest"
                )
            mock_apps.return_value.patch_namespaced_deployment.assert_not_called()

    def test_rolling_back_to_the_current_image_is_allowed(self):
        # It's in history and harmless -- a no-op redeploy, not an error.
        patch = self._run("pennlabs/clubs:current")

        self.assertTrue(patch.called)

    def test_picks_the_matching_container_when_a_sidecar_exists(self):
        containers = [
            SimpleNamespace(name="sidecar", image="datadog/agent:7"),
            SimpleNamespace(name="worker", image="pennlabs/clubs:current"),
        ]

        patch = self._run("pennlabs/clubs:previous", containers=containers)

        # Blindly taking containers[0] would have pointed the sidecar at the
        # application image.
        container = patch.call_args.kwargs["body"]["spec"]["template"]["spec"][
            "containers"
        ][0]
        self.assertEqual(container["name"], "worker")

    def test_refuses_when_the_target_container_is_ambiguous(self):
        containers = [
            SimpleNamespace(name="a", image="pennlabs/clubs:current"),
            SimpleNamespace(name="b", image="pennlabs/clubs:current"),
        ]

        with self.assertRaises(k8s_client.InvalidRollbackTarget):
            self._run("pennlabs/clubs:previous", containers=containers)


class RollbackEndpointValidationTest(LeadClientMixin, TestCase):
    def test_invalid_target_returns_400_not_500(self):
        with mock.patch(
            "deployments.k8s_client.rollback_deployment",
            side_effect=k8s_client.InvalidRollbackTarget("nope"),
        ):
            response = self.client.post(
                "/api/deployments/default/clubs-backend/rollback/",
                data={"image": "attacker/evil:latest"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("nope", response.json()["error"])
