import ProductCard from "../components/ProductCard"
import { useProducts } from "../hooks/useDeployments"

export default function Dashboard() {
  const { data: products, isLoading, error } = useProducts()

  if (isLoading) return <div style={{ padding: 24 }}>Loading...</div>
  if (error)
    return <div style={{ padding: 24, color: "#ef4444" }}>Failed to load products</div>

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: 16,
        padding: 24,
      }}
    >
      {products?.map((p) => <ProductCard key={p.id} product={p} />)}
    </div>
  )
}
