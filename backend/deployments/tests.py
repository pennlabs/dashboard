"""Unit tests for the dashboard API.

The Kubernetes client is mocked out entirely -- these tests verify our view
logic (label-based grouping, dict shaping, error handling) in isolation, with
no real cluster required. Run with:

    python manage.py test
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import requests
from botocore.exceptions import ClientError, EndpointConnectionError
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings
from kubernetes.client.exceptions import ApiException

from django.http import HttpResponseServerError
from django.shortcuts import redirect
from oauthlib.oauth2 import InvalidGrantError, MismatchingStateError
from requests.exceptions import ConnectionError

from deployments import github_client, k8s_client, oauth, pi_client
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


SHA_A = "a" * 40
SHA_B = "b" * 40


def _github_response(status=200, message="Fix login\n\nLonger body", author="Ada"):
    res = requests.Response()
    res.status_code = status
    if status == 200:
        res._content = json.dumps(
            {"commit": {"message": message, "author": {"name": author}}}
        ).encode()
    return res


class GetCommitsTest(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        patcher = mock.patch("deployments.github_client.requests.get")
        self.mock_get = patcher.start()
        self.addCleanup(patcher.stop)

    def test_returns_subject_line_and_author(self):
        self.mock_get.return_value = _github_response()
        self.assertEqual(
            github_client.get_commits("penn-clubs", [SHA_A]),
            {SHA_A: {"message": "Fix login", "author": "Ada"}},
        )
        self.assertEqual(
            self.mock_get.call_args.args[0],
            f"https://api.github.com/repos/pennlabs/penn-clubs/commits/{SHA_A}",
        )

    def test_commit_is_only_fetched_once(self):
        # Commits are immutable, and the unauthenticated limit is 60 an hour.
        self.mock_get.return_value = _github_response()
        github_client.get_commits("penn-clubs", [SHA_A])
        github_client.get_commits("penn-clubs", [SHA_A])
        self.mock_get.assert_called_once()

    def test_same_sha_in_another_repo_is_a_different_commit(self):
        self.mock_get.return_value = _github_response()
        github_client.get_commits("penn-clubs", [SHA_A])
        github_client.get_commits("penn-courses", [SHA_A])
        self.assertEqual(self.mock_get.call_count, 2)

    def test_missing_commit_is_omitted_and_remembered(self):
        self.mock_get.return_value = _github_response(status=404)
        self.assertEqual(github_client.get_commits("private-repo", [SHA_A]), {})
        self.assertEqual(github_client.get_commits("private-repo", [SHA_A]), {})
        self.mock_get.assert_called_once()

    def test_rate_limit_stops_further_calls_but_keeps_cached_commits(self):
        self.mock_get.return_value = _github_response()
        github_client.get_commits("penn-clubs", [SHA_A])

        self.mock_get.reset_mock()
        self.mock_get.return_value = _github_response(status=403)
        result = github_client.get_commits("penn-clubs", [SHA_B, "c" * 40, SHA_A])

        self.assertEqual(list(result), [SHA_A])
        self.mock_get.assert_called_once()

    def test_failure_is_retried_once_the_backoff_expires(self):
        self.mock_get.side_effect = requests.ConnectionError("no route")
        self.assertEqual(github_client.get_commits("penn-clubs", [SHA_A]), {})

        cache.delete(github_client._BACKOFF_KEY)
        self.mock_get.side_effect = None
        self.mock_get.return_value = _github_response()
        self.assertIn(SHA_A, github_client.get_commits("penn-clubs", [SHA_A]))

    @override_settings(GITHUB_TOKEN="secret")
    def test_token_is_sent_when_configured(self):
        self.mock_get.return_value = _github_response()
        github_client.get_commits("penn-clubs", [SHA_A])
        self.assertEqual(
            self.mock_get.call_args.kwargs["headers"]["Authorization"], "Bearer secret"
        )

    @override_settings(GITHUB_TOKEN="")
    def test_no_auth_header_without_a_token(self):
        self.mock_get.return_value = _github_response()
        github_client.get_commits("penn-clubs", [SHA_A])
        self.assertNotIn("Authorization", self.mock_get.call_args.kwargs["headers"])

    def test_commit_with_no_author_still_resolves(self):
        res = _github_response()
        res._content = json.dumps({"commit": {"message": "x", "author": None}}).encode()
        self.mock_get.return_value = res
        self.assertEqual(
            github_client.get_commits("penn-clubs", [SHA_A])[SHA_A]["author"], ""
        )


class DeployedCommitsTest(SimpleTestCase):
    def _replicaset(self, image):
        return SimpleNamespace(
            metadata=SimpleNamespace(
                labels={}, annotations={}, creation_timestamp=None
            ),
            spec=SimpleNamespace(
                template=SimpleNamespace(
                    spec=SimpleNamespace(containers=[SimpleNamespace(image=image)])
                )
            ),
        )

    def test_current_version_first_then_history_without_duplicates(self):
        dep = _fake_deployment("clubs-backend", "default", "penn-clubs", SHA_A)
        history = [
            self._replicaset(f"pennlabs/clubs:{SHA_A}"),
            self._replicaset(f"pennlabs/clubs:{SHA_B}"),
        ]
        self.assertEqual(k8s_client.deployed_commits(dep, history), [SHA_A, SHA_B])

    def test_non_commit_versions_are_skipped(self):
        # Asking GitHub about `latest` or `6.0` would resolve to the wrong thing
        # at best, and waste the rate limit at worst.
        dep = _fake_deployment("pingmobile", "default", "pingmobile", "latest")
        history = [self._replicaset("redis:6.0")]
        self.assertEqual(k8s_client.deployed_commits(dep, history), [])


class DeploymentCommitsApiTest(LeadClientMixin, TestCase):
    url = "/api/deployments/default/clubs-backend/commits/"

    @mock.patch("deployments.github_client.get_commits")
    @mock.patch("deployments.k8s_client.get_replicasets", return_value=[])
    @mock.patch("deployments.k8s_client.get_deployment")
    def test_looks_up_the_deployments_commits_in_its_products_repo(
        self, mock_get, _mock_rs, mock_commits
    ):
        mock_get.return_value = _fake_deployment(
            "clubs-backend", "default", "penn-clubs", SHA_A
        )
        mock_commits.return_value = {SHA_A: {"message": "Fix", "author": "Ada"}}

        res = self.client.get(self.url)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), mock_commits.return_value)
        mock_commits.assert_called_once_with("penn-clubs", [SHA_A])

    @mock.patch(
        "deployments.k8s_client.get_deployment", side_effect=ApiException(status=404)
    )
    def test_unknown_deployment_is_404(self, _mock_get):
        self.assertEqual(self.client.get(self.url).status_code, 404)


class CommitsAccessControlTest(TestCase):
    @mock.patch("deployments.k8s_client.get_deployment")
    def test_anonymous_cannot_read_commits(self, mock_get):
        res = self.client.get("/api/deployments/default/clubs-backend/commits/")
        self.assertEqual(res.status_code, 403)
        mock_get.assert_not_called()


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


class ProductionProxySettingsTest(SimpleTestCase):
    """The OAuth callback must look like https behind the TLS-terminating ingress.

    The callback tests can't catch this: they stub `fetch_token`, and the
    development settings set OAUTHLIB_INSECURE_TRANSPORT, so oauthlib would
    accept an http:// URI anyway. In production neither is true, and an
    http:// callback URI makes oauthlib raise InsecureTransportError.
    """

    def test_forwarded_https_callback_is_rebuilt_as_https(self):
        import importlib
        import os

        from django.test import RequestFactory

        with mock.patch.dict(os.environ, {"SECRET_KEY": "test"}):
            production = importlib.import_module("dashboard.settings.production")

        # What Traefik forwards to the pod: plain HTTP, original scheme in a header.
        request = RequestFactory().get(
            "/api/accounts/callback/?code=abc&state=s",
            HTTP_HOST="dashboard.pennlabs.org",
            HTTP_X_FORWARDED_PROTO="https",
        )
        with override_settings(
            SECURE_PROXY_SSL_HEADER=production.SECURE_PROXY_SSL_HEADER
        ):
            uri = request.build_absolute_uri()

        self.assertTrue(uri.startswith("https://dashboard.pennlabs.org/"), uri)


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


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "nope"}}, "operation")


def _fake_pi_client(values=(1.0, 3.0, None)):
    """A boto3 Performance Insights client with canned answers."""
    start = datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc)
    points = []
    for minute, value in enumerate(values):
        point = {"Timestamp": start + timedelta(minutes=minute)}
        if value is not None:
            point["Value"] = value
        points.append(point)

    by_group = {
        "db.sql_tokenized": {
            "Total": 1.5,
            "Dimensions": {
                "db.sql_tokenized.id": "ABC",
                "db.sql_tokenized.statement": "SELECT ?",
            },
        },
        "db.user": {"Total": 2.0, "Dimensions": {"db.user.name": "penn-courses"}},
        "db.wait_event": {"Total": 0.5, "Dimensions": {"db.wait_event.name": "CPU"}},
    }
    client = mock.Mock()
    client.get_resource_metrics.return_value = {"MetricList": [{"DataPoints": points}]}
    client.describe_dimension_keys.side_effect = lambda **kwargs: {
        "Keys": [by_group[kwargs["GroupBy"]["Group"]]]
    }
    return client


class GetInsightsTest(SimpleTestCase):
    START = datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc)

    def _insights(self, client, window=timedelta(minutes=30)):
        with mock.patch("deployments.pi_client._client", return_value=client):
            return pi_client.get_insights(self.START, self.START + window)

    def test_shapes_the_response(self):
        insights = self._insights(_fake_pi_client())

        self.assertEqual(insights["period_seconds"], 60)
        self.assertEqual(insights["vcpus"], 2)
        self.assertEqual(insights["peak_load"], 3.0)
        self.assertEqual(insights["average_load"], 2.0)
        self.assertEqual(
            insights["queries"],
            [{"id": "ABC", "statement": "SELECT ?", "load": 1.5, "share": 0.75}],
        )
        self.assertEqual(
            insights["users"], [{"name": "penn-courses", "load": 2.0, "share": 1.0}]
        )
        self.assertEqual(insights["waits"], [{"name": "CPU", "load": 0.5, "share": 0.25}])

    def test_a_missing_sample_is_a_gap_not_zero(self):
        insights = self._insights(_fake_pi_client())

        self.assertIsNone(insights["load"][2]["load"])
        # And it doesn't drag the average down either.
        self.assertEqual(insights["average_load"], 2.0)

    def test_no_data_does_not_divide_by_zero(self):
        client = _fake_pi_client(values=())
        client.describe_dimension_keys.side_effect = None
        client.describe_dimension_keys.return_value = {
            "Keys": [{"Total": 0.0, "Dimensions": {"db.user.name": "idle"}}]
        }

        insights = self._insights(client)

        self.assertEqual(insights["peak_load"], 0.0)
        self.assertEqual(insights["average_load"], 0.0)
        self.assertEqual(insights["users"][0]["share"], 0.0)

    def test_shares_are_out_of_every_user_not_just_the_ones_shown(self):
        client = _fake_pi_client()
        users = [
            {"Total": 1.0, "Dimensions": {"db.user.name": f"user-{i}"}}
            for i in range(pi_client.TOP_USERS + 2)
        ]
        client.describe_dimension_keys.side_effect = lambda **kwargs: {
            "Keys": users if kwargs["GroupBy"]["Group"] == "db.user" else []
        }

        insights = self._insights(client)

        self.assertEqual(len(insights["users"]), pi_client.TOP_USERS)
        self.assertEqual(insights["users"][0]["share"], 1 / (pi_client.TOP_USERS + 2))

    def test_times_are_utc_whatever_offset_aws_returns(self):
        eastern = timezone(timedelta(hours=-5))
        client = _fake_pi_client()
        client.get_resource_metrics.return_value = {
            "MetricList": [
                {"DataPoints": [{"Timestamp": datetime(2026, 11, 1, 15, tzinfo=eastern)}]}
            ]
        }

        insights = self._insights(client)

        self.assertEqual(insights["load"][0]["time"], "2026-11-01T20:00:00+00:00")

    def test_every_call_is_scoped_to_the_production_database(self):
        client = _fake_pi_client()
        self._insights(client)

        calls = [client.get_resource_metrics.call_args] + (
            client.describe_dimension_keys.call_args_list
        )
        for call in calls:
            self.assertEqual(call.kwargs["ServiceType"], "RDS")
            self.assertEqual(
                call.kwargs["Identifier"], "db-UZ6WEKHZ2ZTWOOJCPYO3KAQECM"
            )

    def test_period_grows_with_the_window(self):
        for window, period in (
            (timedelta(hours=1), 60),
            (timedelta(hours=6), 60),
            (timedelta(hours=7), 300),
            (timedelta(days=1), 300),
            (timedelta(days=14), 3600),
        ):
            with self.subTest(window=window):
                insights = self._insights(_fake_pi_client(), window)
                self.assertEqual(insights["period_seconds"], period)

    def test_refuses_a_window_over_the_maximum_without_calling_aws(self):
        client = _fake_pi_client()

        with self.assertRaises(pi_client.InvalidWindow):
            self._insights(client, timedelta(days=15))

        client.get_resource_metrics.assert_not_called()

    def test_time_outside_retention_is_an_invalid_window(self):
        client = _fake_pi_client()
        client.get_resource_metrics.side_effect = _client_error(
            "InvalidArgumentException"
        )

        with self.assertRaises(pi_client.InvalidWindow):
            self._insights(client)

    def test_aws_failures_are_reported_as_unavailable(self):
        for failure in (
            _client_error("NotAuthorizedException"),
            EndpointConnectionError(endpoint_url="https://pi.example"),
        ):
            with self.subTest(failure=failure):
                client = _fake_pi_client()
                client.get_resource_metrics.side_effect = failure

                with self.assertRaises(pi_client.PerformanceInsightsUnavailable):
                    self._insights(client)


class DatabaseInsightsApiTest(LeadClientMixin, TestCase):
    URL = "/api/database/insights/"
    WINDOW = {"start": "2026-11-01T20:00:00Z", "end": "2026-11-01T20:30:00Z"}

    def test_passes_the_window_to_performance_insights(self):
        with mock.patch(
            "deployments.pi_client.get_insights", return_value={"load": []}
        ) as get_insights:
            response = self.client.get(self.URL, self.WINDOW)

        self.assertEqual(response.status_code, 200)
        start, end = get_insights.call_args.args
        self.assertEqual(start, datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 11, 1, 20, 30, tzinfo=timezone.utc))

    def test_rejects_bad_times_without_calling_aws(self):
        for params in (
            {},
            {"start": self.WINDOW["start"]},
            {"start": "yesterday", "end": self.WINDOW["end"]},
            # Out of range, which parse_datetime raises on rather than returning None.
            {"start": "2026-13-45T20:00:00Z", "end": self.WINDOW["end"]},
            # No timezone: the same digits are hours apart in UTC and ET.
            {"start": "2026-11-01T20:00:00", "end": "2026-11-01T20:30:00"},
            {"start": self.WINDOW["end"], "end": self.WINDOW["start"]},
        ):
            with self.subTest(params=params):
                with mock.patch("deployments.pi_client.get_insights") as get_insights:
                    response = self.client.get(self.URL, params)

                self.assertEqual(response.status_code, 400)
                get_insights.assert_not_called()

    def test_clamps_end_to_now(self):
        future = datetime.now(timezone.utc) + timedelta(days=1)

        with mock.patch(
            "deployments.pi_client.get_insights", return_value={}
        ) as get_insights:
            self.client.get(
                self.URL,
                {
                    "start": (future - timedelta(days=2)).isoformat(),
                    "end": future.isoformat(),
                },
            )

        self.assertLess(get_insights.call_args.args[1], future)

    def test_invalid_window_is_a_400(self):
        with mock.patch(
            "deployments.pi_client.get_insights",
            side_effect=pi_client.InvalidWindow("too long"),
        ):
            response = self.client.get(self.URL, self.WINDOW)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "too long")

    def test_unavailable_is_a_503_that_hides_the_aws_error(self):
        with mock.patch(
            "deployments.pi_client.get_insights",
            side_effect=pi_client.PerformanceInsightsUnavailable("secret arn"),
        ):
            with self.assertLogs("deployments.views", level="ERROR"):
                response = self.client.get(self.URL, self.WINDOW)

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret arn", response.content.decode())


class DatabaseInsightsAccessTest(TestCase):
    """Query text can hold any product's data, so this is closed to everyone else."""

    URL = "/api/database/insights/"
    WINDOW = DatabaseInsightsApiTest.WINDOW

    def test_refuses_anonymous_visitors(self):
        with mock.patch("deployments.pi_client.get_insights") as get_insights:
            response = Client().get(self.URL, self.WINDOW)

        self.assertEqual(response.status_code, 403)
        get_insights.assert_not_called()

    def test_refuses_signed_in_non_leads(self):
        client = Client()
        client.force_login(_make_user("member", is_lead=False))

        with mock.patch("deployments.pi_client.get_insights") as get_insights:
            response = client.get(self.URL, self.WINDOW)

        self.assertEqual(response.status_code, 403)
        get_insights.assert_not_called()
