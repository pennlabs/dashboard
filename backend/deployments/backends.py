"""Authentication backend: decide who counts as a Penn Labs team lead.

Access to this dashboard is currently limited to team leads. Rather than keep
our own list of pennkeys, we derive it from permissions Platform already tracks.

How that works, end to end:

  1. `pennlabs/infrastructure/docker/team-sync` runs on a cron. It walks the
     GitHub org and treats every team whose slug ends in `-leads` as a lead
     team, mapping `<x>-leads` to the permission codename `<x>_admin` (dashes
     become underscores) -- so `penn-clubs-leads` yields `penn_clubs_admin`.
     Members of the `Directors` team receive every such codename.
  2. team-sync POSTs `{pennkey: [codenames]}` to Platform's
     `/accounts/productadmin/`, which materializes them as Django Permissions.
  3. Platform's `/accounts/introspect/` reports them back to us in the
     `user_permissions` field, which DLA hands to `post_authenticate` below.

Because step 1 only ever issues `*_admin` codenames to lead teams and to
Directors, "holds at least one `*_admin` permission" is exactly equivalent to
"is a lead of some team, or a Director". That is the whole rule.

To widen access later without touching this code, create a `dashboard-leads`
team in the GitHub org: team-sync will start issuing `dashboard_admin`, which
matches the check below just like any other `*_admin` codename.

On top of that, `settings.DASHBOARD_ALLOWED_USERS` names pennkeys that are always
allowed. Two cases need it, and neither is exotic:

  * Whoever operates this dashboard without leading a product team. Step 1 only
    issues codenames to members of a `*-leads` GitHub team who are *also* in
    team-sync's roster.yaml, so a DevOps maintainer has no `*_admin` at all.
  * A Platform lead. Platform's `ProductAdminView` special-cases the
    `platform_admin` slug -- it sets `is_superuser` on the Platform-side user and
    `continue`s *before* creating a Permission -- so `platform_admin` is never
    returned by introspection. Introspection also does not expose `is_staff` or
    `is_superuser` (see Platform's `UserSerializer.Meta.fields`), so there is no
    way for us to infer it. A platform lead who leads nothing else would
    otherwise be refused.
"""

from accounts.backends import LabsUserBackend
from django.conf import settings


class DashboardUserBackend(LabsUserBackend):
    """DLA's backend, plus the team-lead check.

    We record "is a team lead" as `is_staff`/`is_superuser`, which is the
    convention DLA itself uses for its single-permission `ADMIN_PERMISSION`
    gate. `deployments.permissions.IsTeamLead` is what reads it back.
    """

    def post_authenticate(self, user, created, dictionary):
        # `product_permission` is Platform's legacy alias for the same list of
        # codenames; read it as a fallback in case we ever talk to an older
        # Platform deployment.
        permissions = (
            dictionary.get("user_permissions")
            or dictionary.get("product_permission")
            or []
        )
        is_lead = any(codename.endswith("_admin") for codename in permissions)

        # Explicitly allowlisted pennkeys, for the people team-sync's permission
        # pipeline cannot describe. See the module docstring and the setting's
        # comment in settings/base.py.
        allowed = getattr(settings, "DASHBOARD_ALLOWED_USERS", [])
        is_allowlisted = bool(user.username) and user.username.lower() in allowed

        has_access = is_lead or is_allowlisted

        # DLA's `authenticate` has already written is_staff by this point, using
        # its own single-codename ADMIN_PERMISSION test -- which fails for
        # everyone until a `dashboard-leads` team exists. Running last is what
        # makes our broader rule the one that decides.
        #
        # Both grants and revokes, on every login: a lead who has rotated off
        # loses access the next time they sign in. SESSION_COOKIE_AGE bounds how
        # long an already-issued session outlives that change.
        if user.is_staff != has_access:
            user.is_staff = has_access
            user.is_superuser = has_access
            user.save(update_fields=["is_staff", "is_superuser"])
