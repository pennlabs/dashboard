import type { DeploymentEvent } from "../types"

const EVENT_COLORS: Record<DeploymentEvent["event_type"], string> = {
  deploy: "#3b82f6",
  rollback: "#f97316",
  scale: "#6b7280",
}

export default function DeploymentTimeline({
  events,
}: {
  events: DeploymentEvent[]
}) {
  return (
    <ol style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 10 }}>
      {events.map((event) => (
        <li
          key={event.id}
          style={{
            background: "white",
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            padding: 12,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span
              style={{
                background: EVENT_COLORS[event.event_type],
                color: "white",
                borderRadius: 999,
                padding: "2px 8px",
                fontSize: 12,
                textTransform: "uppercase",
              }}
            >
              {event.event_type}
            </span>
            <span style={{ fontFamily: "monospace", fontSize: 13 }}>
              {event.version ? event.version.slice(0, 7) : "-"}
            </span>
            {event.previous_version ? (
              <span style={{ color: "#6b7280", fontFamily: "monospace", fontSize: 12 }}>
                {"<- "}
                {event.previous_version.slice(0, 7)}
              </span>
            ) : null}
          </div>
          <div style={{ marginTop: 6, color: "#6b7280", fontSize: 12 }}>
            {new Date(event.timestamp).toLocaleString()} by {event.triggered_by}
          </div>
        </li>
      ))}
    </ol>
  )
}
