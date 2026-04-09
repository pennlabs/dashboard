import { Link } from "react-router-dom"

import { getHealthStatus, HealthBadge } from "./HealthBadge"
import type { Product } from "../types"

export default function ProductCard({ product }: { product: Product }) {
  const totalReady = product.deployments.reduce(
    (sum, dep) => sum + dep.ready_replicas,
    0
  )
  const totalDesired = product.deployments.reduce(
    (sum, dep) => sum + dep.desired_replicas,
    0
  )
  const lastSynced = product.deployments
    .map((dep) => dep.last_synced)
    .sort((a, b) => new Date(b).getTime() - new Date(a).getTime())[0]

  return (
    <Link
      to={`/products/${product.name}`}
      style={{ textDecoration: "none", color: "inherit" }}
    >
      <div
        style={{
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          padding: 16,
          background: "white",
          display: "grid",
          gap: 8,
        }}
      >
        <h3 style={{ margin: "0 0 8px" }}>{product.display_name}</h3>
        <HealthBadge status={getHealthStatus(totalReady, totalDesired)} />
        <div style={{ color: "#6b7280", fontSize: 13 }}>
          {totalReady}/{totalDesired} replicas
        </div>
        <div style={{ color: "#6b7280", fontSize: 13 }}>
          {product.deployments.length} services
        </div>
        <div style={{ color: "#6b7280", fontSize: 13 }}>
          Last synced: {lastSynced ? new Date(lastSynced).toLocaleTimeString() : "-"}
        </div>
      </div>
    </Link>
  )
}
