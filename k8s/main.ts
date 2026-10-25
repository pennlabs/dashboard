// CDK8s chart describing how this dashboard deploys to Penn Labs' production
// EKS cluster. Build it with:
//
//   RELEASE_NAME=dashboard GIT_SHA=$(git rev-parse HEAD) AWS_ACCOUNT_ID=<acct> npm run build
//
// which emits raw Kubernetes YAML in `dist/`. CI does exactly this and then
// `kubectl apply -f k8s/dist/ --prune -l app.kubernetes.io/part-of=$RELEASE_NAME`.
//
// RELEASE_NAME is not optional: PennLabsChart reads it to set the
// `app.kubernetes.io/part-of` label, which is both how resources are named and
// what `--prune` selects on. Without it every name becomes `undefined_release-*`.
//
// Two workloads: the Django API (with RBAC to read the cluster) and the React
// frontend. The ingress routes /api to Django and / to React, which is why DLA's
// login and callback views are mounted at /api/accounts/ -- no extra ingress
// rule is needed for them.

import { App } from "cdk8s"
import { Construct } from "constructs"
import {
  DjangoApplication,
  PennLabsChart,
  ReactApplication,
} from "@pennlabs/kittyhawk"
// Deep import: kittyhawk doesn't re-export its generated Kubernetes types from
// its index, and we need the same `KubeServiceAccount` type its DeploymentProps
// expects. The package publishes no `exports` map, so this subpath is stable.
import {
  KubeClusterRole,
  KubeClusterRoleBinding,
  KubeServiceAccount,
} from "@pennlabs/kittyhawk/lib/imports/k8s"

// The backend serves on 8000 (gunicorn, see backend/Dockerfile). Kittyhawk
// defaults to 80, which would make the Service target a port nothing listens on.
const BACKEND_PORT = 8000

const HOST = "dashboard.pennlabs.org"

// Send plain-HTTP visitors to HTTPS, via the cluster's shared Traefik
// middleware (the same one platform, penn-clubs and office-hours-queue use).
// Without it http://dashboard.pennlabs.org serves the SPA, but the session and
// CSRF cookies are Secure-only, so sign-in could never stick.
const ingressProps = {
  annotations: {
    "traefik.ingress.kubernetes.io/router.middlewares":
      "default-redirect-http@kubernetescrd",
  },
}

class DashboardChart extends PennLabsChart {
  constructor(scope: Construct) {
    super(scope, "dashboard")

    // ---------------------------------------------------------------- RBAC
    //
    // The whole point of this app is reading live cluster state, and a
    // ServiceAccount has zero API permissions by default -- without the role
    // below, every list call returns 403 and the dashboard renders empty.
    //
    // We declare the ServiceAccount ourselves rather than using kittyhawk's
    // `createServiceAccount: true`, for two reasons:
    //
    //   1. That option is broken. `application/base.js` passes the SA down as
    //      `serviceAccountName` (a string), but `deployment.js` only emits
    //      `serviceAccountName` when `props.serviceAccount` (an object) is set.
    //      So it creates a ServiceAccount and never attaches it -- the pod
    //      silently runs as `default`. Still unfixed upstream as of 1.1.11.
    //   2. It also annotates the SA for IRSA (`eks.amazonaws.com/role-arn`),
    //      which expects a matching IAM role to exist. We don't need one: this
    //      backend calls the Kubernetes API, not any AWS API.
    //
    // These live in the chart rather than a hand-written rbac.yaml so that CI
    // applies them along with everything else. (ClusterRole/ClusterRoleBinding
    // aren't in kubectl's default prune whitelist, so `--prune` leaves them be.)
    //
    // imagePullSecrets: Terraform's eks-bootstrap patches `docker-pull-secret`
    // onto the `default` ServiceAccount only, and that is how every other
    // Penn Labs pod authenticates to Docker Hub. A pod running as this SA does
    // not inherit it, so without restating it here the backend would pull
    // anonymously -- rate-limited, and an ImagePullBackOff if the image is private.
    const serviceAccount = new KubeServiceAccount(this, "backend-sa", {
      metadata: { name: "dashboard-backend" },
      imagePullSecrets: [{ name: "docker-pull-secret" }],
    })

    const clusterRole = new KubeClusterRole(this, "backend-reader", {
      metadata: { name: "dashboard-reader" },
      rules: [
        {
          // Deployments -> the "what's running" view.
          // ReplicaSets  -> rollout history and the rollback target list.
          apiGroups: ["apps"],
          resources: ["deployments", "replicasets"],
          verbs: ["get", "list", "watch"],
        },
        {
          // Pods -> per-pod diagnostics (restart counts, waiting reasons).
          apiGroups: [""],
          resources: ["pods"],
          verbs: ["get", "list", "watch"],
        },
        {
          // The only write verb we grant anywhere. The rollback feature calls
          // AppsV1Api.patch_namespaced_deployment to swap in a previous image;
          // pods and replicasets stay strictly read-only.
          apiGroups: ["apps"],
          resources: ["deployments"],
          verbs: ["patch"],
        },
      ],
    })

    // ClusterRole rather than Role: Penn Labs services span many namespaces and
    // the point is to see all of them in one place.
    new KubeClusterRoleBinding(this, "backend-reader-binding", {
      metadata: { name: "dashboard-reader" },
      subjects: [
        {
          kind: "ServiceAccount",
          name: serviceAccount.name,
          namespace: "default",
        },
      ],
      roleRef: {
        kind: "ClusterRole",
        name: clusterRole.name,
        apiGroup: "rbac.authorization.k8s.io",
      },
    })

    // ---------------------------------------------------------- Django API
    //
    // A single replica, deliberately. Authentication state (users, sessions,
    // OAuth tokens) lives in a SQLite file inside the container, so a session
    // minted on one pod would mean nothing on another and the SPA would
    // intermittently 403. The file is ephemeral by design -- Platform is the
    // source of truth for identity and lead status, so a pod restart just means
    // users silently re-authenticate through their existing Platform SSO
    // session. Moving to Postgres is what would let this scale out again.
    new DjangoApplication(this, "django-api", {
      port: BACKEND_PORT,
      deployment: {
        image: "pennlabs/dashboard-backend",
        replicas: 1,
        // Grants the pod cluster read access via the binding above.
        serviceAccount,
        // `secret` becomes envFrom.secretRef, so every key in the `dashboard`
        // Kubernetes Secret arrives as an environment variable. It must supply
        // SECRET_KEY (signs session cookies -- production refuses to start
        // without it) plus LABS_CLIENT_ID and LABS_CLIENT_SECRET, the OAuth
        // credentials Platform issues for this product. Populated from Vault at
        // secrets/production/default/dashboard by vault-secret-sync.
        secret: "dashboard",
        env: [
          { name: "K8S_IN_CLUSTER", value: "true" },
          // Where Platform sends users back after they authorize. Must match a
          // redirect URI registered on the OAuth client (see README).
          {
            name: "LABS_REDIRECT_URI",
            value: `https://${HOST}/api/accounts/callback/`,
          },
        ],
      },
      djangoSettingsModule: "dashboard.settings.production",
      domains: [{ host: HOST, paths: ["/api"], isSubdomain: true }],
      ingressProps,
    })

    // ----------------------------------------------------- React frontend
    //
    // Static bundle served by nginx.
    new ReactApplication(this, "react", {
      deployment: {
        image: "pennlabs/dashboard-frontend",
        replicas: 2,
        env: [
          // Required, even though the ingress sends /api straight to Django and
          // nginx never actually proxies it here. The image's nginx config has a
          // `proxy_pass ${API_UPSTREAM}` block whose default (`backend:8000`,
          // for docker-compose) does not resolve in-cluster -- and nginx refuses
          // to start on an unresolvable upstream:
          //   [emerg] host not found in upstream "backend"
          // which would crashloop the pod. Point it at the real Service instead.
          {
            name: "API_UPSTREAM",
            value: `http://dashboard-django-api:${BACKEND_PORT}`,
          },
        ],
      },
      domain: { host: HOST, paths: ["/"], isSubdomain: true },
      ingressProps,
    })
  }
}

const app = new App()
new DashboardChart(app)
app.synth()
