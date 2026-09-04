import type { ReactNode } from "react"

import { loginUrl, logoutUrl } from "../api"
import { useAuth } from "../hooks/useAuth"

/**
 * Renders the dashboard only for signed-in Penn Labs team leads.
 *
 * This is a UX gate, not the security boundary -- the API independently rejects
 * everyone else (see deployments/permissions.py). Its job is to show the right
 * screen instead of a wall of failed requests.
 */
export default function AuthGate({ children }: { children: ReactNode }) {
  const { data, isLoading, error } = useAuth()

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
    return (
      <Centered title="Sign in to continue">
        <p className="muted">
          This dashboard shows live deployment state for Penn Labs products.
          Sign in with your PennKey to continue.
        </p>
        {/* A real navigation, not fetch: this is a redirect chain through Platform. */}
        <a className="btn btn-primary" href={loginUrl("/")}>
          Sign in with PennKey
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
        <a className="btn btn-secondary" href={logoutUrl("/")}>
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
