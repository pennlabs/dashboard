import type { Pod } from "../types"

function phaseColor(phase: string): string {
  if (phase === "Running") return "#22c55e"
  if (phase === "Pending") return "#f59e0b"
  if (phase === "Failed" || phase === "Error") return "#ef4444"
  return "#9ca3af"
}

export default function PodStatusList({ pods }: { pods: Pod[] }) {
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {pods.map((pod) => (
        <div
          key={pod.name}
          style={{
            border: "1px solid #e5e7eb",
            background: "white",
            borderRadius: 8,
            padding: 12,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: phaseColor(pod.phase),
              }}
            />
            <span style={{ color: "#6b7280", fontSize: 12 }}>{pod.phase}</span>
            <span style={{ fontFamily: "monospace", fontSize: 13 }}>{pod.name}</span>
          </div>

          <div style={{ display: "grid", gap: 6 }}>
            {pod.containers.map((container) => (
              <div key={container.name} style={{ fontSize: 13 }}>
                <span style={{ fontFamily: "monospace" }}>{container.name}</span>{" "}
                <span style={{ color: container.ready ? "#22c55e" : "#ef4444" }}>
                  {container.ready ? "✓" : "✗"}
                </span>{" "}
                <span style={{ color: "#6b7280" }}>
                  {container.restart_count} restarts
                </span>
                {container.reason ? (
                  <span style={{ color: "#ef4444", fontStyle: "italic", marginLeft: 8 }}>
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
