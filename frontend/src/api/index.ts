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

export const getProduct = (name: string) =>
  apiFetch<Product>(`/api/products/${encodeURIComponent(name)}/`)

export const getDeployment = (namespace: string, name: string) =>
  apiFetch<Deployment>(
    `/api/deployments/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/`
  )

export const getPods = (namespace: string, name: string) =>
  apiFetch<Pod[]>(
    `/api/deployments/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/pods/`
  )

export const rollback = (namespace: string, name: string, image: string) =>
  apiFetch(
    `/api/deployments/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/rollback/`,
    {
      method: "POST",
      body: JSON.stringify({ image }),
    }
  )
