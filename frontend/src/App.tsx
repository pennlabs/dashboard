import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Link, Route, Routes } from "react-router-dom"

import { logoutUrl } from "./api"
import AuthGate from "./components/AuthGate"
import LabsLogo from "./components/LabsLogo"
import ThemeToggle from "./components/ThemeToggle"
import { useAuth } from "./hooks/useAuth"
import Dashboard from "./pages/Dashboard"
import DeploymentDetail from "./pages/DeploymentDetail"
import ProductDetail from "./pages/ProductDetail"
import { ThemeProvider } from "./theme"

const queryClient = new QueryClient()

/** PennKey and a sign-out link, once there's someone to show. */
function UserChip() {
  const { data } = useAuth()
  if (!data?.authenticated || !data.user) return null
  return (
    <span className="user-chip">
      {data.user.pennkey}
      <a href={logoutUrl()}>Sign out</a>
    </span>
  )
}

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
                  <UserChip />
                  <ThemeToggle />
                </div>
              </div>
            </header>
            <main style={{ flex: 1, display: "flex", flexDirection: "column" }}>
              {/* Access is limited to team leads. This is the UX gate; the API
                  enforces the same rule independently. */}
              <AuthGate>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/products/:name" element={<ProductDetail />} />
                  <Route
                    path="/deployments/:namespace/:name"
                    element={<DeploymentDetail />}
                  />
                </Routes>
              </AuthGate>
            </main>
          </div>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
