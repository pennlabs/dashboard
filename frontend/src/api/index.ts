import type { CurrentUser, Deployment, Pod, Product } from "../types"

// Empty by default: the dev server proxies /api to Django (see setupProxy.js) and
// in production nginx and the API sit behind the same host. Same-origin requests
// are what make the session and CSRF cookies work, so only override this if you
// really mean to talk to another origin.
const BASE = process.env.REACT_APP_API_BASE_URL || ""

/** Login and logout are full page navigations -- they redirect through Platform. */
export const loginUrl = (next = "/") =>
  `${BASE}/api/accounts/login/?next=${encodeURIComponent(next)}`

/**
 * Signing out drops our session but NOT the user's Platform SSO session, so the
 * default lands on `/?logged_out=1`. AuthGate treats that marker as "do not
 * auto-redirect to Platform" -- without it, signing out immediately bounces
 * through Platform, gets silently re-authenticated, and sign-out is impossible.
 * Override `next` only if you have handled that.
 */
export const logoutUrl = (next = "/?logged_out=1") =>
  `${BASE}/api/accounts/logout/?next=${encodeURIComponent(next)}`

/** An API error that keeps its status code, so callers can single out a 403. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, path: string) {
    super(`${status} ${path}`)
    this.name = "ApiError"
    this.status = status
  }
}

function readCookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`))
    ?.split("=")[1]
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const method = options?.method ?? "GET"
  const headers: Record<string, string> = { "Content-Type": "application/json" }

  // DRF's SessionAuthentication enforces CSRF, so anything that isn't a safe
  // method needs the token Django set as a cookie. `GET /api/me/` is what seeds
  // it (that view is decorated with @ensure_csrf_cookie).
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    const csrfToken = readCookie("csrftoken")
    if (csrfToken) {
      headers["X-CSRFToken"] = csrfToken
    }
  }

  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    ...options,
    headers: { ...headers, ...options?.headers },
  })
  if (!res.ok) {
    throw new ApiError(res.status, path)
  }
  return res.json()
}

/** Who is signed in, and may they use the dashboard? Always resolves. */
export const getMe = () => apiFetch<CurrentUser>("/api/me/")

export const getProducts = () => apiFetch<Product[]>("/api/products/")

export const getProduct = (name: string) =>
  apiFetch<Product>(`/api/products/${encodeURIComponent(name)}/`)

export const getDeployment = (namespace: string, name: string) =>
  apiFetch<Deployment>(
    `/api/deployments/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/`
  )

export const getPods = (namespace: string, name: string) =>
  apiFetch<Pod[]>(
    `/api/deployments/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/pods/`
  )

export const rollback = (namespace: string, name: string, image: string) =>
  apiFetch(
    `/api/deployments/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/rollback/`,
    {
      method: "POST",
      body: JSON.stringify({ image }),
    }
  )
