import { Link, useParams } from "react-router-dom"

import { getHealthStatus, HealthBadge } from "../components/HealthBadge"
import ProductLogo from "../components/ProductLogo"
import { VersionLink } from "../components/VersionLink"
import { useProduct } from "../hooks/useDeployments"

export default function ProductDetail() {
  const { name = "" } = useParams()
  const { data: product, isLoading, error } = useProduct(name)

  if (isLoading) {
    return (
      <div className="page">
        <div className="skeleton" style={{ height: 80, marginBottom: 16 }} />
        <div className="skeleton" style={{ height: 120 }} />
      </div>
    )
  }
  if (error || !product)
    return (
      <div className="page" style={{ color: "var(--danger)" }}>
        Failed to load product {name}
      </div>
    )

  return (
    <div className="page" style={{ display: "grid", gap: 20 }}>
      <BackLink to="/" label="All products" />

      <div
        className="card"
        style={{
          padding: 20,
          display: "flex",
          gap: 16,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <ProductLogo
          name={product.name}
          displayName={product.display_name}
          size={56}
        />
        <div style={{ flex: 1, minWidth: 240 }}>
          <h2
            style={{
              margin: 0,
              fontSize: 22,
              fontWeight: 700,
            }}
          >
            {product.display_name}
          </h2>
          <a
            href={product.repo_url}
            target="_blank"
            rel="noreferrer"
            className="mono"
            style={{ fontSize: 13 }}
          >
            pennlabs/{product.name} ↗
          </a>
        </div>
        <HealthBadge
          status={
            product.is_healthy
              ? "healthy"
              : product.deployments.some(
                    (d) => d.ready_replicas < d.desired_replicas
                  )
                ? "degraded"
                : "down"
          }
        />
      </div>

      <div>
        <h3 style={{ margin: "0 0 12px", fontSize: 15, fontWeight: 600 }}>
          Deployments ({product.deployments.length})
        </h3>
        <div style={{ display: "grid", gap: 12 }}>
          {product.deployments.map((dep) => {
            const status = getHealthStatus(
              dep.ready_replicas,
              dep.desired_replicas
            )
            const percent =
              dep.desired_replicas === 0
                ? 0
                : Math.round(
                    (dep.ready_replicas / dep.desired_replicas) * 100
                  )
            return (
              <Link
                to={`/deployments/${dep.namespace}/${dep.name}`}
                key={`${dep.namespace}/${dep.name}`}
                className="card-link"
              >
                <div
                  className="card"
                  style={{
                    padding: 16,
                    display: "grid",
                    gap: 12,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      gap: 12,
                      alignItems: "center",
                      justifyContent: "space-between",
                      flexWrap: "wrap",
                    }}
                  >
                    <div style={{ display: "grid", gap: 4, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: 15 }}>
                        {dep.name}
                      </div>
                      <div
                        className="mono"
                        style={{
                          fontSize: 12,
                          color: "var(--text-muted)",
                        }}
                      >
                        ns: {dep.namespace}
                      </div>
                    </div>
                    <HealthBadge status={status} />
                  </div>

                  <div style={{ display: "grid", gap: 6 }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        fontSize: 12,
                        color: "var(--text-secondary)",
                      }}
                    >
                      <span>Replicas</span>
                      <span className="mono" style={{ color: "var(--text)" }}>
                        {dep.ready_replicas}/{dep.desired_replicas}
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
                      gap: 8,
                      fontSize: 13,
                      color: "var(--text-secondary)",
                      paddingTop: 8,
                      borderTop: "1px solid var(--border)",
                    }}
                  >
                    <span>version</span>
                    <VersionLink
                      version={dep.current_version}
                      repoName={product.name}
                    />
                  </div>
                </div>
              </Link>
            )
          })}
        </div>
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
