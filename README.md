# Penn Labs Deployment Dashboard

A real-time deployment monitoring dashboard for Kubernetes. It gives PMs and
developers a single pane of glass for every service running on a cluster:
health, replica counts, deployed git SHAs, pod-level diagnostics, and
ReplicaSet rollout history — all read **live** from the Kubernetes API on
every page load (no database, no sync worker).

## What's in the box

- **Django + DRF backend** that wraps the Kubernetes Python client. Stateless
  — every request hits the K8s API directly, so you always see real-time
  state.
- **React + TypeScript frontend** with React Query for auto-refreshing data
  (every 10–15 s).
- **Multi-stage Docker builds** for both services. The frontend ships as
  nginx + 25 MB of static assets; the backend ships without pip caches or
  build tools.
- **CDK8s / Kittyhawk manifests** describing how the dashboard would deploy
  to a real cluster, plus a hand-written `rbac.yaml` showing the
  least-privilege ClusterRole the backend would need.
- **Sample fake deployments** so anyone can run the dashboard locally on
  `kind` without needing access to a real cloud cluster.
- **Unit tests** that mock the K8s client and verify the API logic in
  isolation.

## Architecture

```
┌──────────────┐         ┌────────────────┐         ┌─────────────────┐
│  React SPA   │ ──HTTP─▶│  Django + DRF  │ ──HTTPS▶│  Kubernetes API │
│ (port 3000)  │◀────────│  (port 8000)   │◀────────│   (live cluster)│
└──────────────┘         └────────────────┘         └─────────────────┘
       browser                  no DB              EKS / kind / minikube
```

There is **no database**. Every API call from the frontend translates into a
fresh request to the Kubernetes API. The label
`app.kubernetes.io/managed-by=kittyhawk` is used as the discovery filter so
the dashboard only surfaces Penn Labs–managed resources, not system pods.

## DevOps concepts demonstrated

| Concept                    | Where it lives                                                           |
| -------------------------- | ------------------------------------------------------------------------ |
| **Containerization**       | `backend/Dockerfile`, `frontend/Dockerfile` (both multi-stage)           |
| **Orchestration**          | `k8s/main.ts` — Kubernetes Deployments + Services + Ingress              |
| **Infrastructure as Code** | CDK8s in TypeScript synthesizes raw K8s YAML                             |
| **RBAC / least privilege** | `k8s/rbac.yaml` — narrowly-scoped ClusterRole                            |
| **Reproducibility**        | Pinned base images; `docker compose up` produces the same env everywhere |
| **Portability**            | Same image runs locally (kind), in EKS, or any K8s cluster               |
| **Testability**            | `backend/deployments/tests.py` with mocked K8s client                    |
| **Observability**          | The dashboard itself is an observability tool                            |

## Quick start (local kind cluster — no AWS needed)

This is the recommended path for graders or anyone without Penn Labs cloud
access. Brings up a real Kubernetes cluster inside a Docker container, loads
fake-but-realistic Deployments, and runs the dashboard against them.

### Prerequisites

- Docker Desktop (running)
- `kubectl`, `kind`, Node.js 18+, Python 3.13
  ```bash
  brew install kubectl kind node python@3.13
  ```

### Run it

```bash
git clone <this-repo>
cd dashboard

# 1. Spin up a local Kubernetes cluster
kind create cluster --config k8s/kind-cluster.yaml

# 2. Load four fake deployments (3 healthy, 1 deliberately broken)
kubectl apply -f k8s/sample-deployments.yaml

# 3. Backend
cd backend
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py runserver &
cd ..

# 4. Frontend
cd frontend
npm install
npm start
```

Open <http://localhost:3000>. You should see three product cards:
`penn-clubs` (green), `ohq` (green), `penn-courses` (red — the broken one,
demonstrating the degraded-health UI). Click in to see pods and ReplicaSet
history.

## Quick start (alternative: docker-compose)

One command instead of separate backend/frontend processes. Mounts your host
kubeconfig read-only into the backend container so it talks to whatever
cluster `kubectl` on your laptop is currently pointed at.

```bash
docker compose up --build
# frontend: http://localhost:3000
# backend:  http://localhost:8000
```

## Running the tests

```bash
cd backend
.venv/bin/python manage.py test
# Ran 8 tests in 0.005s — OK
```

The tests mock the Kubernetes client entirely, so they don't need a cluster.
They verify view logic: label-based product grouping, dict shaping for the
JSON API, 404 handling, and rollback input validation.

## Project structure

```
backend/
├── Dockerfile                       # multi-stage Python build
├── requirements.txt
├── manage.py
├── dashboard/                       # Django project
│   ├── settings/
│   │   ├── base.py                  # shared, no DB, no auth
│   │   ├── development.py           # local: ~/.kube/config, AllowAny
│   │   └── production.py            # in-cluster: ServiceAccount token
│   └── urls.py
└── deployments/                     # the actual app
    ├── k8s_client.py                # all calls to the K8s API live here
    ├── views.py                     # thin DRF views, no business logic
    ├── urls.py                      # routes keyed by (namespace, name)
    └── tests.py                     # unit tests with mocked K8s client

frontend/
├── Dockerfile                       # node build → nginx serve
└── src/
    ├── api/                         # fetch wrappers
    ├── hooks/                       # React Query hooks (auto-refetch)
    ├── pages/                       # Dashboard, ProductDetail, DeploymentDetail
    ├── components/                  # HealthBadge, PodStatusList, RollbackDialog, ...
    └── types/                       # TypeScript shapes mirroring the API

k8s/
├── main.ts                          # CDK8s / Kittyhawk chart
├── package.json                     # `npm run build` synthesizes YAML to dist/
├── rbac.yaml                        # ClusterRole + ClusterRoleBinding
├── sample-deployments.yaml          # fake services for local demos
└── kind-cluster.yaml                # kind cluster config

docker-compose.yml                   # one-command local stack
```

## How K8s discovery works

The dashboard relies on three labels Penn Labs' Kittyhawk library applies to
every managed resource:

| Label                                    | Used for                             |
| ---------------------------------------- | ------------------------------------ |
| `app.kubernetes.io/managed-by=kittyhawk` | Filter — what to show vs. hide       |
| `app.kubernetes.io/part-of=<repo>`       | Group Deployments into "products"    |
| `app.kubernetes.io/version=<git-sha>`    | Display the deployed commit          |
| `app.kubernetes.io/name=<deployment>`    | Find the pods for a given Deployment |

The dashboard wouldn't exist without these conventions — they turn the cluster
into a queryable database. Adding the dashboard cost zero changes to any
existing service.

## RBAC: the production deployment story

If this dashboard ran _inside_ the cluster (the original proposal), its
backend pod would authenticate as a ServiceAccount, which by default has zero
permissions. `k8s/rbac.yaml` shows the narrowest possible ClusterRole that
makes the dashboard work:

- `get`, `list`, `watch` on **deployments** and **replicasets** (apps/v1)
- `get`, `list`, `watch` on **pods** (core/v1)
- `patch` on **deployments** only (the rollback button)

No write access on pods or replicasets. No access to Secrets, ConfigMaps,
Services, or anything else. A bug or an exploit in the dashboard cannot
delete or modify any other workload in the cluster.

For the course demo we run locally, so RBAC isn't applied to a live cluster
— but the file is the deliverable that documents the access control story.

## Synthesizing the production manifests

```bash
cd k8s
npm install
npm run build
# YAML appears in k8s/dist/
```

Inspect `dist/dashboard.k8s.yaml` to see what would actually deploy. Combined
with `rbac.yaml`, this is everything needed to ship the dashboard to a real
cluster.

## Limitations and future work

This project was descoped from a more ambitious original proposal (database +
sync worker + CI/CD pipeline) after instructor feedback that "the simpler the
better." Things that were intentionally cut and would be the natural next
steps:

- **CI/CD via GitHub Actions** — build/test on PR, push images to Docker
  Hub on merge, `kubectl apply` to EKS. Was in the original proposal.
- **Deployment history** — would require adding a small database back, since
  the K8s API doesn't retain deploy events beyond the lifetime of the
  ReplicaSets that produced them (typically ~10 revisions).
- **Production OAuth** — `django-labs-accounts` integration was dropped for
  the local-only demo. Production deployment would re-enable it for access
  control.
- **Alerts** — turn the polling-based dashboard into push-based notifications
  when a deployment becomes unhealthy.
- **Multi-cluster support** — currently the backend reads one kubeconfig
  context at a time. Adding a context switcher would let one dashboard span
  staging + production.

## License

MIT.
