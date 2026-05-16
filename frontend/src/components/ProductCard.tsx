import { Link } from "react-router-dom"

import { getHealthStatus, HealthBadge } from "./HealthBadge"
import ProductLogo from "./ProductLogo"
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
  const status = getHealthStatus(totalReady, totalDesired)
  const percent =
    totalDesired === 0
      ? 0
      : Math.min(100, Math.round((totalReady / totalDesired) * 100))

  const healthy = product.deployments.filter(
    (d) => getHealthStatus(d.ready_replicas, d.desired_replicas) === "healthy"
  ).length

  return (
    <Link to={`/products/${product.name}`} className="card-link">
      <div
        className="card"
        style={{
          padding: 18,
          display: "grid",
          gap: 14,
          minWidth: 0,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 12,
            minWidth: 0,
          }}
        >
          <ProductLogo name={product.name} displayName={product.display_name} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3
              style={{
                margin: 0,
                fontSize: 16,
                fontWeight: 700,
                color: "var(--text)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={product.display_name}
            >
              {product.display_name}
            </h3>
            <div
              className="mono"
              style={{
                fontSize: 12,
                color: "var(--text-muted)",
                marginTop: 2,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              pennlabs/{product.name}
            </div>
          </div>
          <div style={{ flexShrink: 0 }}>
            <HealthBadge status={status} />
          </div>
        </div>

        <div style={{ display: "grid", gap: 6 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 12,
              color: "var(--text-secondary)",
              fontWeight: 500,
            }}
          >
            <span>Replicas</span>
            <span className="mono" style={{ color: "var(--text)" }}>
              {totalReady}/{totalDesired}
            </span>
          </div>
          <div className={`progress ${status}`}>
            <span style={{ width: `${percent}%` }} />
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            paddingTop: 10,
            borderTop: "1px solid var(--border)",
            fontSize: 12,
            color: "var(--text-secondary)",
          }}
        >
          <span>
            <strong style={{ color: "var(--text)" }}>
              {product.deployments.length}
            </strong>{" "}
            deployment{product.deployments.length === 1 ? "" : "s"}
          </span>
          <span>
            <strong style={{ color: "var(--text)" }}>{healthy}</strong> healthy
          </span>
        </div>
      </div>
    </Link>
  )
}
