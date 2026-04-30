import { useState } from "react"
import { Link, useParams } from "react-router-dom"

import { getHealthStatus, HealthBadge } from "../components/HealthBadge"
import PodStatusList from "../components/PodStatusList"
import RollbackDialog from "../components/RollbackDialog"
import { VersionLink } from "../components/VersionLink"
import { useDeployment, usePods, useRollback } from "../hooks/useDeployments"

export default function DeploymentDetail() {
  const { namespace = "", name = "" } = useParams()
  const [showRollback, setShowRollback] = useState(false)

  const { data: dep, isLoading, error } = useDeployment(namespace, name)
  const { data: pods } = usePods(namespace, name)
  const rollbackMutation = useRollback(namespace, name)

  if (isLoading) return <div style={{ padding: 24 }}>Loading...</div>
  if (error || !dep)
    return (
      <div style={{ padding: 24, color: "#991b1b" }}>
        Failed to load deployment {namespace}/{name}
      </div>
    )

  const onConfirmRollback = async (image: string) => {
    await rollbackMutation.mutateAsync(image)
    setShowRollback(false)
  }

  const rolloutInProgress = dep.updated_replicas < dep.desired_replicas

  return (
    <div style={{ padding: 24, display: "grid", gap: 16 }}>
      <Link to={dep.product_name ? `/products/${dep.product_name}` : "/"}>
        {"<-"} Back
      </Link>

      <div style={{ display: "grid", gap: 8 }}>
        <h2 style={{ margin: 0 }}>{dep.name}</h2>
        <code style={{ color: "#6b7280" }}>
          {dep.name}.{dep.namespace}
        </code>
        <HealthBadge status={getHealthStatus(dep.ready_replicas, dep.desired_replicas)} />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
          gap: 12,
          background: "white",
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          padding: 12,
        }}
      >
        <Stat label="Desired" value={dep.desired_replicas} />
        <Stat label="Ready" value={dep.ready_replicas} />
        <Stat label="Available" value={dep.available_replicas} />
        <Stat label="Updated" value={dep.updated_replicas} />
      </div>

      {rolloutInProgress ? (
        <div style={{ display: "grid", gap: 6 }}>
          <div>Rollout in progress...</div>
          <progress
            value={dep.updated_replicas}
            max={dep.desired_replicas}
            style={{ width: "100%" }}
          />
        </div>
      ) : null}

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span>Current version:</span>
        <VersionLink version={dep.current_version} repoName={dep.product_name} />
      </div>

      {dep.replicasets.length > 1 ? (
        <button
          type="button"
          onClick={() => setShowRollback(true)}
          style={{
            background: "#1e3a5f",
            color: "white",
            padding: "8px 16px",
            borderRadius: 4,
            border: "none",
            width: "fit-content",
            cursor: "pointer",
          }}
        >
          Roll back
        </button>
      ) : null}

      <div style={{ display: "grid", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Pods</h3>
        {pods === undefined ? (
          <div style={{ color: "#6b7280" }}>Loading pods...</div>
        ) : pods.length === 0 ? (
          <div style={{ color: "#6b7280" }}>No pods found.</div>
        ) : (
          <PodStatusList pods={pods} />
        )}
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        <h3 style={{ margin: 0 }}>ReplicaSet history</h3>
        <ol
          style={{
            margin: 0,
            padding: 0,
            listStyle: "none",
            display: "grid",
            gap: 6,
          }}
        >
          {dep.replicasets.map((rs) => (
            <li
              key={rs.revision}
              style={{
                background: "white",
                border: "1px solid #e5e7eb",
                borderRadius: 8,
                padding: 10,
                display: "flex",
                alignItems: "center",
                gap: 10,
                flexWrap: "wrap",
                fontSize: 13,
              }}
            >
              <span
                style={{
                  background: "#e5e7eb",
                  borderRadius: 999,
                  padding: "2px 8px",
                  fontFamily: "monospace",
                  fontSize: 12,
                }}
              >
                rev {rs.revision}
              </span>
              <code>{rs.version ? rs.version.slice(0, 7) : "-"}</code>
              <span style={{ color: "#6b7280", fontFamily: "monospace" }}>
                {rs.image}
              </span>
              {rs.created_at ? (
                <span style={{ color: "#9ca3af", marginLeft: "auto" }}>
                  {new Date(rs.created_at).toLocaleString()}
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      </div>

      {showRollback ? (
        <RollbackDialog
          replicasets={dep.replicasets}
          onConfirm={onConfirmRollback}
          onClose={() => setShowRollback(false)}
          isLoading={rollbackMutation.isPending}
        />
      ) : null}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div style={{ color: "#6b7280", fontSize: 12 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600 }}>{value}</div>
    </div>
  )
}
