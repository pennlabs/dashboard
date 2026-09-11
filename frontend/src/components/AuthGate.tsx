import { useEffect } from "react"
import type { ReactNode } from "react"

import { loginUrl, logoutUrl } from "../api"
import { useAuth } from "../hooks/useAuth"

// Reasons the backend attaches as ?auth_error=… when a sign-in fails, rather
// than surfacing a blank 500. Kept in sync with deployments/oauth.py.
const AUTH_ERRORS: Record<string, string> = {
  oauth:
    "Your sign-in link expired or had already been used. Starting again should fix it.",
  unreachable:
    "We couldn't reach Penn Labs Platform to verify your PennKey. It may be briefly unavailable — try again in a moment.",
  platform:
    "Platform couldn't confirm your account. If this keeps happening, ask in #platform.",
}

/**
 * Renders the dashboard only for signed-in Penn Labs team leads.
 *
 * This is a UX gate, not the security boundary -- the API independently rejects
 * everyone else (see deployments/permissions.py). Its job is to show the right
 * screen instead of a wall of failed requests.
 *
 * Signing in is the first thing that happens to a visitor with no session: we
 * send them straight to Platform rather than showing a "sign in" button first.
 * That mirrors Platform's own frontend, which does the same in
 * `frontend/utils/auth.tsx` -- `withAuth` redirects to `/accounts/login/?next=…`
 * the moment `/accounts/me/` comes back non-ok. Platform can do that server-side
 * in getServerSideProps; this app is a static bundle behind nginx, so the
 * earliest equivalent is as soon as /api/me/ answers.
 */
export default function AuthGate({ children }: { children: ReactNode }) {
  const { data, isLoading, error } = useAuth()

  const params = new URLSearchParams(window.location.search)
  // Why the last attempt failed, if it did.
  const authError = params.get("auth_error")
  // Set by the "Sign out" links below, via ?next=.
  const justLoggedOut = params.has("logged_out")

  // Both flags suppress the auto-redirect, and both have to. Without them the
  // user ends up in a loop they cannot break out of:
  //   * a failed sign-in lands back here still unauthenticated, so we would
  //     bounce to Platform again, fail again, and spin;
  //   * signing out drops our session but not Platform's SSO session, so we
  //     would bounce to Platform, be silently signed straight back in, and
  //     land on "you don't have access yet" -- making sign-out impossible.
  const shouldRedirect = Boolean(
    !isLoading && !error && data && !data.authenticated && !authError && !justLoggedOut
  )

  useEffect(() => {
    if (!shouldRedirect) return
    // `next` is the page they actually asked for, so they land there rather than
    // at the root -- the same thing Platform passes as `?next=${ctx.resolvedUrl}`.
    // The backend re-validates it as same-origin regardless (oauth.safe_next).
    const next = window.location.pathname + window.location.search
    // replace(), not assign(): the pre-login URL should not become a back-button
    // stop that bounces the user through Platform again.
    window.location.replace(loginUrl(next))
  }, [shouldRedirect])

  if (isLoading) {
    return <Centered>Checking your access…</Centered>
  }

  // /api/me/ is public and always 200s, so a failure here means the API itself
  // is unreachable rather than anything to do with permissions.
  if (error || !data) {
    return (
      <Centered title="Can't reach the dashboard API">
        <p className="muted">
          The backend didn't respond. If you're running locally, check that it
          started.
        </p>
      </Centered>
    )
  }

  if (!data.authenticated) {
    // The effect above is already navigating to Platform; this is the frame or
    // two before the browser leaves the page.
    if (shouldRedirect) {
      return <Centered>Redirecting you to PennKey sign-in…</Centered>
    }

    if (justLoggedOut) {
      return (
        <Centered title="You've signed out">
          <p className="muted">
            Your dashboard session is over. Note your Penn Labs SSO session may
            still be active, so signing in again may not re-prompt for your
            PennKey.
          </p>
          {/* A real navigation, not fetch: this is a redirect chain through Platform. */}
          <a className="btn btn-primary" href={loginUrl("/")}>
            Sign in again
          </a>
        </Centered>
      )
    }

    // Only reached with ?auth_error=<reason>: the backend sends failures back
    // here rather than rendering a blank 500 (see deployments/oauth.py). No
    // automatic retry -- that is what would loop -- so offer a manual one.
    return (
      <Centered title="Sign-in didn't complete">
        <p className="muted">{AUTH_ERRORS[authError!] ?? AUTH_ERRORS.oauth}</p>
        <a className="btn btn-primary" href={loginUrl("/")}>
          Try again
        </a>
      </Centered>
    )
  }

  if (!data.is_lead) {
    const name = data.user?.first_name || data.user?.pennkey
    return (
      <Centered title="You don't have access yet">
        <p className="muted">
          You're signed in{name ? ` as ${name}` : ""}, but the dashboard is
          currently limited to Penn Labs team leads. If you lead a team and are
          seeing this, your Platform permissions may not have synced yet — ask
          in #platform.
        </p>
        <a className="btn btn-secondary" href={logoutUrl()}>
          Sign out
        </a>
      </Centered>
    )
  }

  return <>{children}</>
}

function Centered({
  title,
  children,
}: {
  title?: string
  children: ReactNode
}) {
  return (
    <div className="auth-gate">
      <div className="auth-gate-card">
        {title && <h1>{title}</h1>}
        {children}
      </div>
    </div>
  )
}
