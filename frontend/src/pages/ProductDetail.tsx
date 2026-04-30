import { Link, useParams } from "react-router-dom"

import { getHealthStatus, HealthBadge } from "../components/HealthBadge"
import { VersionLink } from "../components/VersionLink"
import { useProduct } from "../hooks/useDeployments"

export default function ProductDetail() {
  const { name = "" } = useParams()
  const { data: product, isLoading, error } = useProduct(name)

  if (isLoading) return <div style={{ padding: 24 }}>Loading...</div>
  if (error || !product)
    return (
      <div style={{ padding: 24, color: "#991b1b" }}>
        Failed to load product {name}
      </div>
    )

  return (
    <div style={{ padding: 24, display: "grid", gap: 16 }}>
      <Link to="/">{"<-"} Back</Link>
      <div>
        <h2 style={{ margin: "0 0 8px" }}>{product.display_name}</h2>
        <a href={product.repo_url} target="_blank" rel="noreferrer">
          pennlabs/{product.name}
        </a>
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        {product.deployments.map((dep) => (
          <Link
            to={`/deployments/${dep.namespace}/${dep.name}`}
            key={`${dep.namespace}/${dep.name}`}
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              background: "white",
              padding: 12,
              display: "grid",
              gap: 6,
              textDecoration: "none",
              color: "inherit",
            }}
          >
            <div style={{ fontWeight: 600 }}>{dep.name}</div>
            <div style={{ color: "#6b7280", fontSize: 12 }}>
              namespace: <code>{dep.namespace}</code>
            </div>
            <HealthBadge
              status={getHealthStatus(dep.ready_replicas, dep.desired_replicas)}
            />
            <div style={{ color: "#6b7280", fontSize: 13 }}>
              {dep.ready_replicas}/{dep.desired_replicas} replicas
            </div>
            <VersionLink version={dep.current_version} repoName={product.name} />
          </Link>
        ))}
      </div>
    </div>
  )
}
