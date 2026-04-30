import ProductCard from "../components/ProductCard"
import { useProducts } from "../hooks/useDeployments"

export default function Dashboard() {
  const { data: products, isLoading, error, isFetching } = useProducts()

  if (isLoading) {
    return <SkeletonGrid />
  }
  if (error) {
    return (
      <div style={{ padding: 24 }}>
        <ErrorBox
          title="Failed to load products"
          detail={(error as Error).message}
        />
      </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: 16,
          color: "#6b7280",
          fontSize: 13,
        }}
      >
        <span>
          {products?.length ?? 0} products
        </span>
        <span>{isFetching ? "Refreshing..." : "Auto-refreshing every 15s"}</span>
      </div>

      {products && products.length === 0 ? (
        <div
          style={{
            border: "1px dashed #d1d5db",
            borderRadius: 8,
            padding: 24,
            color: "#6b7280",
            background: "white",
          }}
        >
          No Kittyhawk-managed deployments found in the current cluster. If
          you're testing locally with kind, run:
          <pre style={{ background: "#f3f4f6", padding: 12, borderRadius: 6 }}>
            kubectl apply -f k8s/sample-deployments.yaml
          </pre>
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: 16,
          }}
        >
          {products?.map((p) => <ProductCard key={p.name} product={p} />)}
        </div>
      )}
    </div>
  )
}

function SkeletonGrid() {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: 16,
        padding: 24,
      }}
    >
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          style={{
            height: 120,
            background: "white",
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            padding: 16,
            opacity: 0.6,
          }}
        />
      ))}
    </div>
  )
}

function ErrorBox({ title, detail }: { title: string; detail: string }) {
  return (
    <div
      style={{
        border: "1px solid #fecaca",
        background: "#fef2f2",
        color: "#991b1b",
        padding: 16,
        borderRadius: 8,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <code style={{ fontSize: 12 }}>{detail}</code>
    </div>
  )
}
