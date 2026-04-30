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
//   - No `secret: "dashboard"` because there are no DB credentials.
//   - Two workloads only: the Django API (with RBAC) + the React frontend.

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
    new DjangoApplication(this, "django-api", {
      deployment: {
        image: "pennlabs/dashboard-backend",
        replicas: 2,
        env: [{ name: "K8S_IN_CLUSTER", value: "true" }],
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
