"""Hardened wrappers around django-labs-accounts' OAuth views.

DLA's login/callback views handle the happy path well but fail badly at the
edges, and every failure surfaces to the user as a blank HTTP 500. Since this
dashboard is internet-facing, each of those is a real user-visible defect:

  * `CallbackView.get` does `request.session.pop("state")` with no default, so
    arriving at the callback without a session raises KeyError -> 500. That is
    not an exotic case: a stale bookmark, cleared cookies, a session older than
    SESSION_COOKIE_AGE, or starting the flow in one browser and finishing in
    another all produce it.
  * An expired, reused or tampered authorization code makes `fetch_token` raise
    an oauthlib error -> 500. A mismatched `state` (the OAuth CSRF defence) is
    the security-relevant case and must be rejected, not ignored.
  * If Platform is unreachable or introspection returns non-200, DLA returns a
    bare `HttpResponseServerError()` with no body at all.
  * `next` is validated only with `startswith("/")`, which accepts the
    protocol-relative `//evil.com`. `redirect()` then emits
    `Location: //evil.com`, which browsers follow off-site -- an open redirect
    on a login endpoint, i.e. a ready-made phishing link that begins with a
    genuine pennlabs.org URL. `LogoutView` has the identical flaw, and is just
    as reachable, so it gets the same treatment.

Rather than reimplement the flow (and risk diverging from DLA's token handling),
these subclasses sanitise the input going in and translate failures coming out.
Failures redirect to the SPA with `?auth_error=<reason>`; the frontend renders a
retry screen. That keeps error presentation in the SPA and avoids needing a
Django template layer this project doesn't otherwise have.
"""

import logging

from accounts.views import CallbackView, LoginView, LogoutView
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

# Where the SPA lives. Failures come back here with a reason attached.
SPA_ROOT = "/"


def safe_next(raw: str) -> str:
    """A `next` value that can only ever point back at this site.

    `url_has_allowed_host_and_scheme` with no allowed hosts accepts only
    same-origin relative paths, rejecting `//evil.com`, `https://evil.com` and
    backslash tricks alike. Django uses it for exactly this purpose in its own
    auth views.
    """
    if raw and url_has_allowed_host_and_scheme(raw, allowed_hosts=None):
        return raw
    return SPA_ROOT


def _failed(reason: str):
    """Send the user back to the SPA with a reason it can render."""
    return redirect(f"{SPA_ROOT}?auth_error={reason}")


class DashboardLoginView(LoginView):
    """DLA's login view, with `next` restricted to this site."""

    def get(self, request):
        raw = request.GET.get("next", SPA_ROOT)
        cleaned = safe_next(raw)
        if cleaned != raw:
            logger.warning("Rejected unsafe next parameter: %r", raw)
        # DLA reads `next` back off request.GET, so hand it a sanitised copy.
        request.GET = request.GET.copy()
        request.GET["next"] = cleaned
        return super().get(request)


class DashboardCallbackView(CallbackView):
    """DLA's callback view, with every failure mode given a real response."""

    def get(self, request):
        # Restart the flow rather than KeyError. The user most likely bookmarked
        # the callback or lost their session; sending them to login is both the
        # correct recovery and what they were trying to do anyway.
        if "state" not in request.session:
            logger.info("Callback hit without an OAuth state; restarting login")
            return redirect(f"{reverse('accounts:login')}?next={SPA_ROOT}")

        try:
            response = super().get(request)
        except OAuth2Error as exc:
            # Covers MismatchingStateError (OAuth CSRF), InvalidGrantError
            # (expired/replayed code) and friends. Never silently continue.
            logger.warning("OAuth exchange failed: %s", exc)
            request.session.pop("state", None)
            return _failed("oauth")
        except RequestException as exc:
            logger.error("Could not reach Platform during sign-in: %s", exc)
            request.session.pop("state", None)
            return _failed("unreachable")

        # DLA signals "introspection failed" or "no user" with a bare 500.
        if response.status_code >= 500:
            logger.error("Platform rejected the sign-in (status %s)", response.status_code)
            return _failed("platform")

        return response


class DashboardLogoutView(LogoutView):
    """DLA's logout view, with `next` restricted to this site.

    Logout takes a `next` and validates it with the same `startswith("/")` test as
    login, so `/api/accounts/logout/?next=//evil.com` is an open redirect too --
    and an unauthenticated one, since logging out needs no session.
    """

    def get(self, request):
        raw = request.GET.get("next", SPA_ROOT)
        cleaned = safe_next(raw)
        if cleaned != raw:
            logger.warning("Rejected unsafe next parameter on logout: %r", raw)
        request.GET = request.GET.copy()
        request.GET["next"] = cleaned
        return super().get(request)
