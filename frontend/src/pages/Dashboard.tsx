import { useMemo, useState } from "react"

import { getHealthStatus } from "../components/HealthBadge"
import ProductCard from "../components/ProductCard"
import { useProducts } from "../hooks/useDeployments"
import type { HealthStatus, Product } from "../types"

type Filter = "all" | HealthStatus

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "healthy", label: "Healthy" },
  { id: "degraded", label: "Degraded" },
  { id: "down", label: "Down" },
  { id: "unknown", label: "Unknown" },
]

function productStatus(product: Product): HealthStatus {
  const ready = product.deployments.reduce((s, d) => s + d.ready_replicas, 0)
  const desired = product.deployments.reduce(
    (s, d) => s + d.desired_replicas,
    0
  )
  return getHealthStatus(ready, desired)
}

export default function Dashboard() {
  const { data: products, isLoading, error, isFetching } = useProducts()
  const [filter, setFilter] = useState<Filter>("all")
  const [query, setQuery] = useState("")

  const counts = useMemo(() => {
    const c: Record<Filter, number> = {
      all: products?.length ?? 0,
      healthy: 0,
      degraded: 0,
      down: 0,
      unknown: 0,
    }
    products?.forEach((p) => {
      c[productStatus(p)] += 1
    })
    return c
  }, [products])

  const filtered = useMemo(() => {
    if (!products) return []
    const q = query.trim().toLowerCase()
    return products.filter((p) => {
      const status = productStatus(p)
      if (filter !== "all" && status !== filter) return false
      if (!q) return true
      return (
        p.name.toLowerCase().includes(q) ||
        p.display_name.toLowerCase().includes(q)
      )
    })
  }, [products, filter, query])

  if (isLoading) return <SkeletonGrid />
  if (error) {
    return (
      <div className="page">
        <ErrorBox
          title="Failed to load products"
          detail={(error as Error).message}
        />
      </div>
    )
  }

  return (
    <div className="page">
      <div style={{ marginBottom: 18 }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700 }}>Products</h1>
        <p
          style={{
            margin: "6px 0 0",
            color: "var(--text-secondary)",
            fontSize: 14,
          }}
        >
          {products?.length ?? 0} products tracked ·{" "}
          {isFetching ? "Refreshing…" : "Auto-refreshing every 15s"}
        </p>
      </div>

      <div className="toolbar">
        <div className="search">
          <SearchIcon />
          <input
            type="search"
            placeholder="Search products…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="filter-group" role="group" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              className="filter-pill"
              aria-pressed={filter === f.id}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
              <span className="count">{counts[f.id]}</span>
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        products && products.length === 0 ? (
          <EmptyClusterHint />
        ) : (
          <EmptyFilterHint
            onClear={() => {
              setFilter("all")
              setQuery("")
            }}
          />
        )
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
            gap: 18,
          }}
        >
          {filtered.map((p) => (
            <ProductCard key={p.name} product={p} />
          ))}
        </div>
      )}
    </div>
  )
}

function SearchIcon() {
  return (
    <svg
      className="search-icon"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  )
}

function SkeletonGrid() {
  return (
    <div className="page">
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
          gap: 18,
        }}
      >
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton" style={{ height: 168 }} />
        ))}
      </div>
    </div>
  )
}

function EmptyClusterHint() {
  return (
    <div
      className="card"
      style={{
        padding: 28,
        textAlign: "center",
        color: "var(--text-secondary)",
      }}
    >
      <div style={{ fontWeight: 600, color: "var(--text)", marginBottom: 6 }}>
        No deployments found
      </div>
      <p style={{ margin: "0 0 12px" }}>
        No Kittyhawk-managed deployments exist in the current cluster. If you're
        testing locally with kind, run:
      </p>
      <pre
        className="mono"
        style={{
          margin: 0,
          background: "var(--surface-2)",
          padding: 12,
          borderRadius: 8,
          fontSize: 13,
          color: "var(--text)",
          textAlign: "left",
          display: "inline-block",
        }}
      >
        kubectl apply -f k8s/sample-deployments.yaml
      </pre>
    </div>
  )
}

function EmptyFilterHint({ onClear }: { onClear: () => void }) {
  return (
    <div
      className="card"
      style={{
        padding: 28,
        textAlign: "center",
        color: "var(--text-secondary)",
      }}
    >
      <div style={{ fontWeight: 600, color: "var(--text)", marginBottom: 6 }}>
        No products match these filters
      </div>
      <p style={{ margin: "0 0 14px" }}>Try a different status or clear the search.</p>
      <button type="button" className="btn btn-secondary" onClick={onClear}>
        Clear filters
      </button>
    </div>
  )
}

function ErrorBox({ title, detail }: { title: string; detail: string }) {
  return (
    <div
      style={{
        border: "1px solid color-mix(in srgb, var(--danger) 40%, transparent)",
        background: "var(--danger-soft)",
        color: "var(--danger)",
        padding: 16,
        borderRadius: 12,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <code style={{ fontSize: 12 }}>{detail}</code>
    </div>
  )
}
