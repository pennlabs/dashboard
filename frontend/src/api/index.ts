import type { Deployment, Pod, Product } from "../types"

const BASE = process.env.REACT_APP_API_BASE_URL || "http://localhost:8000"

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`${res.status} ${path}`)
  }
  return res.json()
}

export const getProducts = () => apiFetch<Product[]>("/api/products/")
export const getProduct = (name: string) => apiFetch<Product>(`/api/products/${name}/`)
export const getDeployment = (id: number) =>
  apiFetch<Deployment>(`/api/deployments/${id}/`)
export const getPods = (id: number) => apiFetch<Pod[]>(`/api/deployments/${id}/pods/`)
export const rollback = (id: number, image: string) =>
  apiFetch(`/api/deployments/${id}/rollback/`, {
    method: "POST",
    body: JSON.stringify({ image }),
  })
