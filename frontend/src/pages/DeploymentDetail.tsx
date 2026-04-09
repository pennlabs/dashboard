import { useMemo, useState } from "react"
import { Link, useParams } from "react-router-dom"

import DeploymentTimeline from "../components/DeploymentTimeline"
import { getHealthStatus, HealthBadge } from "../components/HealthBadge"
import PodStatusList from "../components/PodStatusList"
import RollbackDialog from "../components/RollbackDialog"
import { VersionLink } from "../components/VersionLink"
import { useDeployment, usePods, useRollback } from "../hooks/useDeployments"

export default function DeploymentDetail() {
  const { id } = useParams()
  const deploymentId = useMemo(() => Number(id), [id])
  const [showRollback, setShowRollback] = useState(false)

  const { data: dep, isLoading, error } = useDeployment(deploymentId)
  const { data: pods } = usePods(deploymentId)
  const rollbackMutation = useRollback(deploymentId)

  if (isLoading) return <div style={{ padding: 24 }}>Loading...</div>
  if (error || !dep)
    return <div style={{ padding: 24, color: "#ef4444" }}>Failed to load deployment</div>

  const onConfirmRollback = async (image: string) => {
    await rollbackMutation.mutateAsync(image)
    setShowRollback(false)
  }

  return (
    <div style={{ padding: 24, display: "grid", gap: 16 }}>
      <Link to={dep.product_name ? `/products/${dep.product_name}` : "/"}>Back</Link>

      <div style={{ display: "grid", gap: 8 }}>
        <h2 style={{ margin: 0 }}>{dep.name}</h2>
        <code>
          {dep.name}.{dep.namespace}
        </code>
        <HealthBadge status={getHealthStatus(dep.ready_replicas, dep.desired_replicas)} />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
          gap: 12,
        }}
      >
        <div>Desired: {dep.desired_replicas}</div>
        <div>Ready: {dep.ready_replicas}</div>
        <div>Available: {dep.available_replicas}</div>
        <div>Updated: {dep.updated_replicas}</div>
      </div>

      {dep.updated_replicas < dep.desired_replicas ? (
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
          }}
        >
          Roll back
        </button>
      ) : null}

      <div style={{ display: "grid", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Pods</h3>
        <PodStatusList pods={pods ?? []} />
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Timeline</h3>
        <DeploymentTimeline events={dep.events} />
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
