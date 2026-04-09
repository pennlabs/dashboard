import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Route, Routes } from "react-router-dom"

import Dashboard from "./pages/Dashboard"
import DeploymentDetail from "./pages/DeploymentDetail"
import ProductDetail from "./pages/ProductDetail"

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div
          style={{
            minHeight: "100vh",
            background: "#f9fafb",
            fontFamily: "system-ui, sans-serif",
          }}
        >
          <header
            style={{
              background: "#1e3a5f",
              color: "white",
              padding: "12px 24px",
              fontSize: "18px",
              fontWeight: 600,
            }}
          >
            Penn Labs Deployments
          </header>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/products/:name" element={<ProductDetail />} />
            <Route path="/deployments/:id" element={<DeploymentDetail />} />
          </Routes>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
