// CDK8s chart describing how this dashboard would be deployed to Penn Labs'
// production EKS cluster. We don't actually deploy from this file for the
// course demo (we run locally), but it's kept as a deliverable artifact:
//
//   npm run build
//
// emits raw Kubernetes YAML in `dist/` that any cluster admin could
// `kubectl apply -f` to deploy this dashboard.
//
// Compared to the original proposal this is intentionally simpler:
//   - The "sync worker" pod is gone (we read live, no DB sync needed).
//   - Two workloads only: the Django API (with RBAC) + the React frontend.
//
// The API needs a `dashboard` secret for OAuth (see below). Note the ingress
// already routes /api to Django, which is why DLA's login and callback views are
// mounted at /api/accounts/ -- no extra ingress rule is needed for them.

import { App } from "cdk8s"
import { Construct } from "constructs"
import {
  DjangoApplication,
  PennLabsChart,
  ReactApplication,
} from "@pennlabs/kittyhawk"

class DashboardChart extends PennLabsChart {
  constructor(scope: Construct) {
    super(scope, "dashboard")

    // Django API.
    //
    // The backend talks to the Kubernetes API server using the in-cluster
    // ServiceAccount token mounted at /var/run/secrets/kubernetes.io/serviceaccount.
    // `createServiceAccount: true` makes Kittyhawk emit a SA; the ClusterRole
    // and ClusterRoleBinding granting it read access live in `rbac.yaml`
    // (raw YAML, kept readable for the course writeup).
    // A single replica, deliberately. Authentication state (users, sessions,
    // OAuth tokens) lives in a SQLite file inside the container, so a session
    // minted on one pod would mean nothing on another and the SPA would
    // intermittently 403. The file is ephemeral by design -- Platform is the
    // source of truth for identity and lead status, so a pod restart just means
    // users silently re-authenticate through their existing Platform SSO
    // session. Moving to Postgres is what would let this scale out again.
    new DjangoApplication(this, "django-api", {
      deployment: {
        image: "pennlabs/dashboard-backend",
        replicas: 1,
        // `secret` becomes envFrom.secretRef, so every key in the `dashboard`
        // Kubernetes Secret arrives as an environment variable. It must supply
        // SECRET_KEY (signs session cookies -- production refuses to start
        // without it) plus LABS_CLIENT_ID and LABS_CLIENT_SECRET, the OAuth
        // credentials Platform issues for this product. All from Vault.
        secret: "dashboard",
        env: [
          { name: "K8S_IN_CLUSTER", value: "true" },
          // Where Platform sends users back after they authorize. Must match a
          // redirect URI registered on the OAuth client (see README).
          {
            name: "LABS_REDIRECT_URI",
            value: "https://dashboard.pennlabs.org/api/accounts/callback/",
          },
        ],
      },
      djangoSettingsModule: "dashboard.settings.production",
      domains: [
        { host: "dashboard.pennlabs.org", paths: ["/api"], isSubdomain: true },
      ],
      createServiceAccount: true,
    })

    // Static React frontend served by nginx.
    new ReactApplication(this, "react", {
      deployment: {
        image: "pennlabs/dashboard-frontend",
        replicas: 2,
      },
      domain: {
        host: "dashboard.pennlabs.org",
        paths: ["/"],
        isSubdomain: true,
      },
    })
  }
}

const app = new App()
new DashboardChart(app)
app.synth()
