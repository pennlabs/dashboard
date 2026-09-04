import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Link, Route, Routes } from "react-router-dom"

import LabsLogo from "./components/LabsLogo"
import ThemeToggle from "./components/ThemeToggle"
import Dashboard from "./pages/Dashboard"
import DeploymentDetail from "./pages/DeploymentDetail"
import ProductDetail from "./pages/ProductDetail"
import { ThemeProvider } from "./theme"

const queryClient = new QueryClient()

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <div className="app-shell">
            <header className="app-header">
              <div className="app-header-inner">
                <Link to="/" className="brand">
                  <LabsLogo />
                  <span>Deployments</span>
                </Link>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span className="live-pill">
                    <span className="dot" />
                    live from kubernetes
                  </span>
                  <ThemeToggle />
                </div>
              </div>
            </header>
            <main style={{ flex: 1 }}>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/products/:name" element={<ProductDetail />} />
                <Route
                  path="/deployments/:namespace/:name"
                  element={<DeploymentDetail />}
                />
              </Routes>
            </main>
          </div>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
