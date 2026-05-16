import type { Pod } from "../types"

function phaseClass(phase: string): string {
  if (phase === "Running") return "healthy"
  if (phase === "Pending") return "degraded"
  if (phase === "Failed" || phase === "Error") return "down"
  return "unknown"
}

export default function PodStatusList({ pods }: { pods: Pod[] }) {
  return (
    <div style={{ display: "grid", gap: 10 }}>
      {pods.map((pod) => (
        <div key={pod.name} className="card" style={{ padding: 14 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              marginBottom: 10,
              flexWrap: "wrap",
            }}
          >
            <span className={`status-badge ${phaseClass(pod.phase)}`}>
              <span className="dot" />
              {pod.phase}
            </span>
            <span
              className="mono"
              style={{ fontSize: 13, color: "var(--text)" }}
            >
              {pod.name}
            </span>
          </div>

          <div style={{ display: "grid", gap: 6 }}>
            {pod.containers.map((container) => (
              <div
                key={container.name}
                style={{
                  fontSize: 13,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  flexWrap: "wrap",
                }}
              >
                <span
                  className="mono"
                  style={{ color: "var(--text)", fontWeight: 500 }}
                >
                  {container.name}
                </span>
                <span
                  style={{
                    color: container.ready
                      ? "var(--success)"
                      : "var(--danger)",
                    fontWeight: 600,
                  }}
                >
                  {container.ready ? "✓ ready" : "✗ not ready"}
                </span>
                <span style={{ color: "var(--text-muted)" }}>
                  · {container.restart_count} restarts
                </span>
                {container.reason ? (
                  <span
                    style={{
                      color: "var(--danger)",
                      fontStyle: "italic",
                    }}
                  >
                    {container.reason}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
