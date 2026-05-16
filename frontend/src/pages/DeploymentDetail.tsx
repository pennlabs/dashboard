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

  if (isLoading)
    return (
      <div className="page">
        <div className="skeleton" style={{ height: 80, marginBottom: 16 }} />
        <div className="skeleton" style={{ height: 240 }} />
      </div>
    )
  if (error || !dep)
    return (
      <div className="page" style={{ color: "var(--danger)" }}>
        Failed to load deployment {namespace}/{name}
      </div>
    )

  const onConfirmRollback = async (image: string) => {
    await rollbackMutation.mutateAsync(image)
    setShowRollback(false)
  }

  const status = getHealthStatus(dep.ready_replicas, dep.desired_replicas)
  const rolloutInProgress = dep.updated_replicas < dep.desired_replicas

  return (
    <div className="page" style={{ display: "grid", gap: 20 }}>
      <BackLink
        to={dep.product_name ? `/products/${dep.product_name}` : "/"}
        label={dep.product_name ? `Back to ${dep.product_name}` : "All products"}
      />

      <div
        className="card"
        style={{
          padding: 20,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "grid", gap: 6 }}>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>
            {dep.name}
          </h2>
          <code style={{ color: "var(--text-muted)", fontSize: 13 }}>
            {dep.name}.{dep.namespace}
          </code>
        </div>
        <HealthBadge status={status} />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: 12,
        }}
      >
        <Stat label="Desired" value={dep.desired_replicas} />
        <Stat label="Ready" value={dep.ready_replicas} />
        <Stat label="Available" value={dep.available_replicas} />
        <Stat label="Updated" value={dep.updated_replicas} />
      </div>

      {rolloutInProgress ? (
        <div
          className="card"
          style={{ padding: 14, display: "grid", gap: 8 }}
        >
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            Rollout in progress…{" "}
            <span className="mono" style={{ color: "var(--text)" }}>
              {dep.updated_replicas}/{dep.desired_replicas}
            </span>
          </div>
          <div className="progress degraded">
            <span
              style={{
                width: `${
                  dep.desired_replicas === 0
                    ? 0
                    : Math.round(
                        (dep.updated_replicas / dep.desired_replicas) * 100
                      )
                }%`,
              }}
            />
          </div>
        </div>
      ) : null}

      <div
        className="card"
        style={{
          padding: 16,
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Current version
        </span>
        <VersionLink
          version={dep.current_version}
          repoName={dep.product_name}
        />
        {dep.replicasets.length > 1 ? (
          <button
            type="button"
            onClick={() => setShowRollback(true)}
            className="btn btn-primary"
            style={{ marginLeft: "auto" }}
          >
            Roll back
          </button>
        ) : null}
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Pods</h3>
        {pods === undefined ? (
          <div className="card" style={{ padding: 16, color: "var(--text-muted)" }}>
            Loading pods…
          </div>
        ) : pods.length === 0 ? (
          <div className="card" style={{ padding: 16, color: "var(--text-muted)" }}>
            No pods found.
          </div>
        ) : (
          <PodStatusList pods={pods} />
        )}
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
          ReplicaSet history
        </h3>
        <ol
          style={{
            margin: 0,
            padding: 0,
            listStyle: "none",
            display: "grid",
            gap: 8,
          }}
        >
          {dep.replicasets.map((rs) => (
            <li
              key={rs.revision}
              className="card"
              style={{
                padding: 12,
                display: "flex",
                alignItems: "center",
                gap: 10,
                flexWrap: "wrap",
                fontSize: 13,
              }}
            >
              <span
                className="mono"
                style={{
                  background: "var(--surface-2)",
                  borderRadius: 999,
                  padding: "2px 10px",
                  fontSize: 11,
                  color: "var(--text-secondary)",
                  border: "1px solid var(--border)",
                }}
              >
                rev {rs.revision}
              </span>
              <code style={{ color: "var(--text)" }}>
                {rs.version ? rs.version.slice(0, 7) : "-"}
              </code>
              <span className="mono" style={{ color: "var(--text-muted)" }}>
                {rs.image}
              </span>
              {rs.created_at ? (
                <span
                  style={{
                    color: "var(--text-muted)",
                    marginLeft: "auto",
                    fontSize: 12,
                  }}
                >
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
    <div
      className="card"
      style={{
        padding: 14,
      }}
    >
      <div
        style={{
          color: "var(--text-muted)",
          fontSize: 11,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          fontWeight: 600,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 22,
          fontWeight: 700,
          marginTop: 4,
          color: "var(--text)",
        }}
      >
        {value}
      </div>
    </div>
  )
}

function BackLink({ to, label }: { to: string; label: string }) {
  return (
    <Link
      to={to}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 13,
        color: "var(--text-secondary)",
        width: "fit-content",
      }}
    >
      <span aria-hidden="true">←</span> {label}
    </Link>
  )
}
