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

export interface DeploymentEvent {
  id: number
  version: string
  previous_version: string
  event_type: "deploy" | "rollback" | "scale"
  timestamp: string
  triggered_by: string
}

export interface ReplicaSetSnapshot {
  id: number
  version: string
  image: string
  revision: number
  created_at: string
}

export interface DeploymentSummary {
  id: number
  name: string
  namespace: string
  current_version: string
  desired_replicas: number
  ready_replicas: number
  is_healthy: boolean
  last_synced: string
}

export interface Deployment extends DeploymentSummary {
  product_name: string
  available_replicas: number
  updated_replicas: number
  events: DeploymentEvent[]
  replicasets: ReplicaSetSnapshot[]
}

export interface Product {
  id: number
  name: string
  display_name: string
  repo_url: string
  is_healthy: boolean
  deployments: DeploymentSummary[]
}
