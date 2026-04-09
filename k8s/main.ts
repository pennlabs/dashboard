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

    new DjangoApplication(this, "django-api", {
      deployment: {
        image: "pennlabs/dashboard-backend",
        replicas: 2,
        secret: "dashboard",
        env: [{ name: "K8S_IN_CLUSTER", value: "true" }],
      },
      djangoSettingsModule: "dashboard.settings.production",
      domains: [{ host: "dashboard.pennlabs.org", paths: ["/api"], isSubdomain: true }],
      createServiceAccount: true,
    })

    new DjangoApplication(this, "sync-worker", {
      deployment: {
        image: "pennlabs/dashboard-backend",
        replicas: 1,
        secret: "dashboard",
        cmd: ["python", "manage.py", "sync_k8s"],
        env: [{ name: "K8S_IN_CLUSTER", value: "true" }],
        noContainerPorts: true,
      },
      djangoSettingsModule: "dashboard.settings.production",
      createServiceAccount: true,
    })

    new ReactApplication(this, "react", {
      deployment: {
        image: "pennlabs/dashboard-frontend",
        replicas: 2,
        env: [
          {
            name: "REACT_APP_API_BASE_URL",
            value: "https://dashboard.pennlabs.org",
          },
        ],
      },
      domain: { host: "dashboard.pennlabs.org", paths: ["/"], isSubdomain: true },
    })
  }
}

const app = new App()
new DashboardChart(app)
app.synth()
