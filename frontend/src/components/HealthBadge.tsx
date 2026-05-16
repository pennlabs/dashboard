import type { HealthStatus } from "../types"

export function getHealthStatus(ready: number, desired: number): HealthStatus {
  if (desired === 0) return "unknown"
  if (ready === 0) return "down"
  if (ready < desired) return "degraded"
  return "healthy"
}

const LABEL: Record<HealthStatus, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  down: "Down",
  unknown: "Unknown",
}

export function HealthBadge({ status }: { status: HealthStatus }) {
  return (
    <span className={`status-badge ${status}`}>
      <span className="dot" />
      {LABEL[status]}
    </span>
  )
}
