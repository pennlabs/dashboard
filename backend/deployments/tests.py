"""Unit tests for the dashboard API.

The Kubernetes client is mocked out entirely -- these tests verify our view
logic (label-based grouping, dict shaping, error handling) in isolation, with
no real cluster required. Run with:

    python manage.py test
"""

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from kubernetes.client.exceptions import ApiException

from django.http import HttpResponseServerError
from django.shortcuts import redirect
from oauthlib.oauth2 import InvalidGrantError, MismatchingStateError
from requests.exceptions import ConnectionError

from deployments import k8s_client, oauth
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


@override_settings(DASHBOARD_ALLOWED_USERS=["chenstan"])
class AllowlistedUserTest(TestCase):
    """`DASHBOARD_ALLOWED_USERS` grants access without any `*_admin` codename.

    team-sync only issues those codenames to members of a GitHub `*-leads` team
    who are also in its roster.yaml, so a maintainer who leads no product team
    has none -- and a Platform lead has none either, because Platform's
    ProductAdminView sets is_superuser for `platform_admin` instead of creating a
    Permission. Both are locked out by the `*_admin` test alone.
    """

    def _post_authenticate(self, user, permissions):
        DashboardUserBackend().post_authenticate(
            user, created=False, dictionary={"user_permissions": permissions}
        )
        user.refresh_from_db()
        return user

    def test_allowlisted_user_with_no_permissions_gets_access(self):
        user = self._post_authenticate(_make_user("chenstan", is_lead=False), [])
        self.assertTrue(user.is_staff)

    def test_allowlist_match_is_case_insensitive(self):
        # Platform returns whatever casing the user record holds; team-sync
        # lowercases pennkeys, so the setting is normalised and this must match.
        user = self._post_authenticate(_make_user("ChenStan", is_lead=False), [])
        self.assertTrue(user.is_staff)

    def test_allowlisted_user_is_not_demoted_on_relogin(self):
        # The revocation branch must not claw back access it just granted.
        user = self._post_authenticate(_make_user("chenstan", is_lead=True), [])
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_non_allowlisted_user_with_no_permissions_is_still_denied(self):
        # The allowlist is additive; it must not widen access to anyone else.
        user = self._post_authenticate(_make_user("someoneelse", is_lead=False), [])
        self.assertFalse(user.is_staff)

    def test_lead_who_is_not_allowlisted_still_gets_access(self):
        user = self._post_authenticate(
            _make_user("clubslead", is_lead=False), ["penn_clubs_admin"]
        )
        self.assertTrue(user.is_staff)

    @override_settings(DASHBOARD_ALLOWED_USERS=[])
    def test_empty_allowlist_denies_everyone_without_a_codename(self):
        user = self._post_authenticate(_make_user("chenstan", is_lead=False), [])
        self.assertFalse(user.is_staff)


class AllowlistSettingTest(SimpleTestCase):
    """The shipped default must actually contain the operator's pennkey."""

    def test_chenstan_is_allowed_by_default(self):
        from django.conf import settings

        self.assertIn("chenstan", settings.DASHBOARD_ALLOWED_USERS)

    def test_entries_are_normalised(self):
        from django.conf import settings

        for pennkey in settings.DASHBOARD_ALLOWED_USERS:
            with self.subTest(pennkey=pennkey):
                self.assertEqual(pennkey, pennkey.strip().lower())
                self.assertTrue(pennkey)


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

    def test_commit_shaped_tags_are_versions(self):
        self.assertTrue(k8s_client.looks_like_commit("c196b60332d25b8de9ca30192c541d38fd739c3c"))
        self.assertTrue(k8s_client.looks_like_commit("201449bebe"))

    def test_non_commit_tags_are_not_versions(self):
        # All observed in the real cluster.
        for tag in ("6.0", "6.2.6-v6", "latest", "1.25-alpine", ""):
            with self.subTest(tag=tag):
                self.assertFalse(k8s_client.looks_like_commit(tag))


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

    def test_upstream_image_tag_is_not_used_as_a_version(self):
        # `redis:6.0` -> "" so the UI shows a dash, not a link to /commit/6.0.
        rs = _fake_replicaset(4, "redis:6.0")

        self.assertEqual(k8s_client.replicaset_to_dict(rs)["version"], "")

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

    # Real Kittyhawk images are tagged with the full deploying commit. Using
    # `:current`/`:previous` here would be a fixture that never occurs in the
    # cluster -- exactly the kind of mismatch that hid the history bug.
    CURRENT = "pennlabs/clubs:c196b60332d25b8de9ca30192c541d38fd739c3c"
    PREVIOUS = "pennlabs/clubs:de2329cf49d943c651f14e883b30e6a259f72d51"

    def setUp(self):
        self.history = [
            _fake_replicaset(3, self.CURRENT, name="rs3"),
            _fake_replicaset(2, self.PREVIOUS, name="rs2"),
        ]

    def _run(self, image, containers=None, history=None):
        containers = containers or [SimpleNamespace(name="worker", image=self.CURRENT)]
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
        patch = self._run(self.PREVIOUS)

        body = patch.call_args.kwargs["body"]
        container = body["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["name"], "worker")
        self.assertEqual(container["image"], self.PREVIOUS)

    def test_also_updates_the_version_label(self):
        # The dashboard reads current_version from this label. Patching only the
        # image left the UI showing the pre-rollback SHA -- the rollback looked
        # like a no-op even though the older image was running.
        patch = self._run(self.PREVIOUS)

        body = patch.call_args.kwargs["body"]
        self.assertEqual(
            body["metadata"]["labels"]["app.kubernetes.io/version"],
            "de2329cf49d943c651f14e883b30e6a259f72d51",
        )

    def test_no_version_label_written_for_untagged_image(self):
        history = [_fake_replicaset(2, "pennlabs/clubs", name="rs2")]

        patch = self._run("pennlabs/clubs", history=history)

        self.assertNotIn("metadata", patch.call_args.kwargs["body"])

    def test_version_label_untouched_for_upstream_image(self):
        # Real case from production: the per-product Redis Deployments run
        # `redis:6.0` but their version label holds the release's commit. Writing
        # "6.0" into that label would destroy real information and make the UI
        # link to a commit that doesn't exist.
        history = [_fake_replicaset(2, "redis:6.0", name="rs2")]

        patch = self._run("redis:6.0", history=history)

        body = patch.call_args.kwargs["body"]
        self.assertNotIn("metadata", body)
        # The image itself is still rolled back.
        self.assertEqual(
            body["spec"]["template"]["spec"]["containers"][0]["image"], "redis:6.0"
        )

    def test_version_label_replaces_a_non_commit_label(self):
        # pingmobile-backend's label is literally "latest" while its image tag is
        # a real commit -- rolling back should correct that.
        history = [_fake_replicaset(2, "pennlabs/ping:201449bebe", name="rs2")]

        patch = self._run("pennlabs/ping:201449bebe", history=history)

        self.assertEqual(
            patch.call_args.kwargs["body"]["metadata"]["labels"][
                "app.kubernetes.io/version"
            ],
            "201449bebe",
        )

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
        patch = self._run(self.CURRENT)

        self.assertTrue(patch.called)

    def test_picks_the_matching_container_when_a_sidecar_exists(self):
        containers = [
            SimpleNamespace(name="sidecar", image="datadog/agent:7"),
            SimpleNamespace(name="worker", image=self.CURRENT),
        ]

        patch = self._run(self.PREVIOUS, containers=containers)

        # Blindly taking containers[0] would have pointed the sidecar at the
        # application image.
        container = patch.call_args.kwargs["body"]["spec"]["template"]["spec"][
            "containers"
        ][0]
        self.assertEqual(container["name"], "worker")

    def test_refuses_when_the_target_container_is_ambiguous(self):
        containers = [
            SimpleNamespace(name="a", image=self.CURRENT),
            SimpleNamespace(name="b", image=self.CURRENT),
        ]

        with self.assertRaises(k8s_client.InvalidRollbackTarget):
            self._run(self.PREVIOUS, containers=containers)


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


class OAuthNextSanitizationTest(TestCase):
    """`next` must never be able to send a user off-site.

    DLA validates only `startswith("/")`, which accepts the protocol-relative
    `//evil.com`; browsers follow that off-site, turning the login endpoint into
    an open redirect whose URL begins with a genuine pennlabs.org host.
    """

    def test_safe_relative_paths_are_kept(self):
        for value in ("/", "/products/penn-clubs", "/deployments/default/x/"):
            with self.subTest(value=value):
                self.assertEqual(oauth.safe_next(value), value)

    def test_offsite_targets_are_replaced_with_root(self):
        for value in (
            "//evil.example.com",
            "https://evil.example.com",
            "http://evil.example.com",
            "/\\evil.example.com",
            "",
        ):
            with self.subTest(value=value):
                self.assertEqual(oauth.safe_next(value), "/")

    def test_login_does_not_redirect_offsite_for_signed_in_user(self):
        # The reachable version of the bug: an authenticated user hitting login
        # is redirected straight to `next`.
        client = Client()
        client.force_login(_make_user("redir", is_lead=True))

        response = client.get("/api/accounts/login/?next=//evil.example.com")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_login_preserves_a_safe_next(self):
        client = Client()
        client.force_login(_make_user("redir", is_lead=True))

        response = client.get("/api/accounts/login/?next=/products/ohq")

        self.assertEqual(response.headers["Location"], "/products/ohq")

    def test_logout_does_not_redirect_offsite(self):
        # Logout has the same `startswith("/")` flaw as login, and needs no
        # session to reach -- so it is an unauthenticated open redirect.
        response = Client().get("/api/accounts/logout/?next=//evil.example.com")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_logout_preserves_a_safe_next(self):
        # The SPA relies on this marker surviving: it is what stops AuthGate from
        # auto-redirecting a just-signed-out user back through Platform SSO.
        response = Client().get("/api/accounts/logout/?next=/%3Flogged_out%3D1")

        self.assertEqual(response.headers["Location"], "/?logged_out=1")

    def test_logout_actually_ends_the_session(self):
        client = Client()
        client.force_login(_make_user("bye", is_lead=True))
        self.assertTrue(client.get("/api/me/").json()["authenticated"])

        client.get("/api/accounts/logout/?next=/%3Flogged_out%3D1")

        self.assertFalse(client.get("/api/me/").json()["authenticated"])


class OAuthCallbackFailureTest(TestCase):
    """Every failure path must produce a real response, never a blank 500."""

    def test_callback_without_a_session_restarts_login(self):
        # Stale bookmark, cleared cookies, or a session older than
        # SESSION_COOKIE_AGE. DLA raises KeyError('state') here -> HTTP 500.
        response = Client().get("/api/accounts/callback/?code=abc&state=xyz")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/api/accounts/login/", response.headers["Location"])

    def _callback_with_state(self, side_effect=None, return_value=None):
        client = Client()
        session = client.session
        session["state"] = "expected-state"
        session["next"] = "/"
        session.save()
        target = "deployments.oauth.CallbackView.get"
        with mock.patch(target, side_effect=side_effect, return_value=return_value):
            return client.get("/api/accounts/callback/?code=abc&state=expected-state")

    def test_expired_or_replayed_code_shows_an_error(self):
        response = self._callback_with_state(side_effect=InvalidGrantError())

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/?auth_error=oauth")

    def test_state_mismatch_is_rejected(self):
        # The OAuth CSRF defence. Must fail closed, not be swallowed.
        response = self._callback_with_state(side_effect=MismatchingStateError())

        self.assertEqual(response.headers["Location"], "/?auth_error=oauth")

    def test_unreachable_platform_shows_an_error(self):
        response = self._callback_with_state(side_effect=ConnectionError())

        self.assertEqual(response.headers["Location"], "/?auth_error=unreachable")

    def test_platform_rejection_shows_an_error(self):
        # DLA signals introspection failure with a bare HttpResponseServerError.
        response = self._callback_with_state(
            return_value=HttpResponseServerError("")
        )

        self.assertEqual(response.headers["Location"], "/?auth_error=platform")

    def test_successful_callback_is_passed_through_untouched(self):
        response = self._callback_with_state(return_value=redirect("/"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")


@override_settings(DASHBOARD_ALLOWED_USERS=["chenstan"])
class EndToEndSignInTest(TestCase):
    """The real sign-in flow, with Platform mocked only at the HTTP boundary.

    The other callback tests stub `CallbackView.get` wholesale, so they never run
    DLA's own logic. This one does, which is the point: DLA's `authenticate`
    writes `is_staff` itself from its single-codename ADMIN_PERMISSION test
    (`dashboard_admin`, which nothing issues today) and saves the user *before*
    calling `post_authenticate`. If our hook ever stopped running last, or DLA
    reordered those two steps, every non-lead grant would silently regress to
    False -- and only a test that exercises both halves together would notice.
    """

    def _sign_in(self, username, permissions, pennid=42):
        client = Client()
        session = client.session
        session["state"] = "expected-state"
        session["next"] = "/"
        session.save()

        token = {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
        introspection = mock.Mock(status_code=200)
        introspection.json.return_value = {
            "user": {
                "pennid": pennid,
                "username": username,
                "first_name": "Test",
                "last_name": "User",
                "email": f"{username}@upenn.edu",
                "groups": [],
                "user_permissions": permissions,
            }
        }

        # Patch the methods on requests_oauthlib's session class, so DLA's view
        # code runs unmodified and only the network calls are replaced.
        with mock.patch(
            "accounts.views.OAuth2Session.fetch_token", return_value=token
        ), mock.patch(
            "accounts.views.OAuth2Session.post", return_value=introspection
        ):
            response = client.get("/api/accounts/callback/?code=abc&state=expected-state")
        return client, response

    def test_allowlisted_operator_ends_up_with_a_working_session(self):
        client, response = self._sign_in("chenstan", permissions=[])

        # Landed back on the SPA, not on an error.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

        # DLA cleared is_staff on its way through; our hook set it back.
        user = User.objects.get(username="chenstan")
        self.assertTrue(user.is_staff)

        # And the session is genuinely usable against a gated endpoint.
        me = client.get("/api/me/").json()
        self.assertTrue(me["authenticated"])
        self.assertTrue(me["is_lead"])
        with mock.patch("deployments.k8s_client.list_deployments", return_value=[]):
            self.assertEqual(client.get("/api/products/").status_code, 200)

    def test_team_lead_ends_up_with_a_working_session(self):
        client, _ = self._sign_in("clubslead", permissions=["penn_clubs_admin"])

        self.assertTrue(User.objects.get(username="clubslead").is_staff)
        self.assertTrue(client.get("/api/me/").json()["is_lead"])

    def test_ordinary_member_is_signed_in_but_refused(self):
        # Authentication succeeds, authorization does not -- the SPA relies on
        # being able to tell these apart to pick the right screen.
        client, response = self._sign_in("member", permissions=[])

        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.get(username="member").is_staff)

        me = client.get("/api/me/").json()
        self.assertTrue(me["authenticated"])
        self.assertFalse(me["is_lead"])
        with mock.patch("deployments.k8s_client.list_deployments", return_value=[]):
            self.assertEqual(client.get("/api/products/").status_code, 403)
