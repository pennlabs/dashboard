# Penn Labs Deploy Dashboard

A deployment monitoring dashboard for Penn Labs infrastructure. Gives PMs and developers real-time visibility into all Kubernetes deployments across Penn Labs products running on AWS EKS.

## Features

- Health status overview for all Penn Labs products (penn-clubs, penn-courses, OHQ, penn-mobile, platform, etc.)
- Replica counts (desired/ready/available/updated) with rollout progress
- Deployed git SHA with links to GitHub commits
- Deployment event timeline (deploys, rollbacks)
- Pod status with container-level details (ready state, restart counts, error reasons)
- One-click rollback to previous versions (admin-only)
- Auto-refreshing data (frontend polls every 10-15s, backend syncs K8s every 30s)

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   React SPA │────>│  Django API  │<────│ Sync Worker │
│  (frontend) │     │  (backend)   │     │  (backend)  │
└─────────────┘     └──────┬───────┘     └──────┬──────┘
                           │                     │
                      PostgreSQL            K8s API
                      (prod) /              (read-only)
                      SQLite (dev)
```

- **Frontend:** React 18 + TypeScript, TanStack React Query v5, React Router v6
- **Backend API:** Django 4.2, Django REST Framework, django-labs-accounts (Penn Labs OAuth)
- **Sync Worker:** Django management command (`sync_k8s`) that continuously syncs K8s state to the database
- **K8s Manifests:** CDK8s with @pennlabs/kittyhawk

## Project Structure

```
backend/
  dashboard/          # Django project settings & URLs
  deployments/        # Main app: models, views, serializers, K8s client
    k8s_client.py     # All Kubernetes API interactions
    management/commands/sync_k8s.py  # Background sync worker
frontend/
  src/
    api/              # API client functions
    components/       # React components (HealthBadge, PodStatusList, etc.)
    hooks/            # React Query hooks
    pages/            # Dashboard, ProductDetail, DeploymentDetail
    types/            # TypeScript interfaces
k8s/
  main.ts             # Kittyhawk CDK8s manifests
```

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 18+
- Access to Penn Labs AWS EKS cluster (for sync worker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate --settings=dashboard.settings.development
python manage.py runserver --settings=dashboard.settings.development
```

API available at `http://localhost:8000`. Test with `curl http://localhost:8000/api/health/`.

### Sync Worker

Requires `kubectl` access to the Penn Labs EKS cluster:

```bash
# Configure AWS CLI with Penn Labs credentials
aws configure --profile pennlabs

# Set up kubeconfig
aws eks update-kubeconfig --name production --region us-east-1 \
  --role-arn arn:aws:iam::449445102765:role/kubectl --profile pennlabs

# Verify access
kubectl get nodes

# Run sync worker (separate terminal)
cd backend
source .venv/bin/activate
python manage.py sync_k8s --settings=dashboard.settings.development
```

### Frontend

```bash
cd frontend
npm install
npm start
```

Opens at `http://localhost:3000`.

## API Endpoints

| Endpoint                          | Method | Auth          | Description                                 |
| --------------------------------- | ------ | ------------- | ------------------------------------------- |
| `/api/health/`                    | GET    | None          | Health check                                |
| `/api/products/`                  | GET    | Authenticated | List all products with deployments          |
| `/api/products/<name>/`           | GET    | Authenticated | Product detail                              |
| `/api/deployments/<id>/`          | GET    | Authenticated | Deployment detail with events & replicasets |
| `/api/deployments/<id>/pods/`     | GET    | Authenticated | Live pod status from K8s                    |
| `/api/deployments/<id>/rollback/` | POST   | Admin         | Rollback to a previous image                |

## K8s Resource Discovery

All Penn Labs resources deployed by Kittyhawk have these labels:

- `app.kubernetes.io/managed-by=kittyhawk` — used as label selector to find all resources
- `app.kubernetes.io/part-of={repo-name}` — groups resources by product
- `app.kubernetes.io/version={git-sha}` — the deployed commit SHA
