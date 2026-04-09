import type { HealthStatus } from "../types"

export function getHealthStatus(ready: number, desired: number): HealthStatus {
  if (desired === 0) return "unknown"
  if (ready === 0) return "down"
  if (ready < desired) return "degraded"
  return "healthy"
}

const COLORS: Record<HealthStatus, string> = {
  healthy: "#22c55e",
  degraded: "#f59e0b",
  down: "#ef4444",
  unknown: "#9ca3af",
}

export function HealthBadge({ status }: { status: HealthStatus }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: COLORS[status],
          display: "inline-block",
        }}
      />
      <span style={{ fontSize: "13px", color: "#374151" }}>{status}</span>
    </span>
  )
}
