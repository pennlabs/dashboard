// Mirrors the JSON shapes the Django API returns.
//
// Note: deployments are identified by (namespace, name) -- the same way
// kubectl identifies them -- not by a database id, because there is no
// database. The frontend uses these two strings as React keys and route
// params.

export type HealthStatus = "healthy" | "degraded" | "down" | "unknown"

export interface ContainerStatus {
  name: string
  ready: boolean
  restart_count: number
  reason: string | null
}

export interface Pod {
  name: string
  phase: string
  start_time: string | null
  containers: ContainerStatus[]
}

export interface ReplicaSetSnapshot {
  revision: number
  version: string
  image: string
  created_at: string | null
}

export interface DeploymentSummary {
  name: string
  namespace: string
  product_name: string
  current_version: string
  desired_replicas: number
  ready_replicas: number
  available_replicas: number
  updated_replicas: number
  is_healthy: boolean
}

export interface Deployment extends DeploymentSummary {
  replicasets: ReplicaSetSnapshot[]
}

export interface Product {
  name: string
  display_name: string
  repo_url: string
  is_healthy: boolean
  deployments: DeploymentSummary[]
}

export interface UserProfile {
  pennkey: string
  first_name: string
  last_name: string
  email: string
}

/**
 * Response from /api/me/. Always resolves, so the two "no access" cases stay
 * distinguishable: not signed in at all, versus signed in but not a team lead.
 */
export interface CurrentUser {
  authenticated: boolean
  is_lead: boolean
  user: UserProfile | null
}
