# Penn Labs Deployment Dashboard

A real-time deployment monitoring dashboard for Kubernetes. It gives PMs and
developers a single pane of glass for every service running on a cluster:
health, replica counts, deployed git SHAs, pod-level diagnostics, and
ReplicaSet rollout history — all read **live** from the Kubernetes API on
every page load (no sync worker, nothing cached).

Sign-in is PennKey SSO through Penn Labs' Platform, and access is currently
limited to team leads — see [Authentication](#authentication).

## What's in the box

- **Django + DRF backend** that wraps the Kubernetes Python client. Stateless
  — every request hits the K8s API directly, so you always see real-time
  state.
- **React + TypeScript frontend** with React Query for auto-refreshing data
  (every 10–15 s).
- **Multi-stage Docker builds** for both services. The frontend ships as
  nginx + 25 MB of static assets; the backend ships a resolved virtualenv
  with no package-manager caches or build tools.
- **CDK8s / Kittyhawk manifests** describing how the dashboard would deploy
  to a real cluster, including the least-privilege ClusterRole the backend
  needs to read the cluster.
- **Sample fake deployments** so anyone can run the dashboard locally on
  `kind` without needing access to a real cloud cluster.
- **Penn Labs SSO** via `django-labs-accounts`, with authorization derived from
  the product-admin permissions Platform already tracks — so "team leads only"
  needs no separate list of pennkeys to maintain.
- **Unit tests** that mock the K8s client and verify both the API logic and the
  access-control rules in isolation.

## Architecture

```
┌──────────────┐         ┌────────────────┐         ┌─────────────────┐
│  React SPA   │ ──HTTP─▶│  Django + DRF  │ ──HTTPS▶│  Kubernetes API │
│ (port 3000)  │◀────────│  (port 8000)   │◀────────│   (live cluster)│
└──────────────┘         └───────┬────────┘         └─────────────────┘
       browser                   │                  EKS / kind / minikube
                                 │ OAuth2 + introspection
                                 ▼
                       ┌──────────────────────┐
                       │ platform.pennlabs.org│
                       │  (PennKey identity)  │
                       └──────────────────────┘
```

**No deployment data is ever persisted.** Every API call from the frontend
translates into a fresh request to the Kubernetes API. The label
`app.kubernetes.io/managed-by=kittyhawk` is used as the discovery filter so
the dashboard only surfaces Penn Labs–managed resources, not system pods.

There *is* a small SQLite database, but only for authentication — Django's
user/session tables plus the OAuth token tables. See
[Authentication](#authentication).

## DevOps concepts demonstrated

| Concept                    | Where it lives                                                           |
| -------------------------- | ------------------------------------------------------------------------ |
| **Containerization**       | `backend/Dockerfile`, `frontend/Dockerfile` (both multi-stage)           |
| **Orchestration**          | `k8s/main.ts` — Kubernetes Deployments + Services + Ingress              |
| **Infrastructure as Code** | CDK8s in TypeScript synthesizes raw K8s YAML                             |
| **RBAC / least privilege** | `k8s/main.ts` — narrowly-scoped ClusterRole + bound ServiceAccount        |
| **SSO / authorization**    | Penn Labs OAuth2 via `django-labs-accounts`; access limited to team leads (`deployments/backends.py`, `deployments/permissions.py`) |
| **Reproducibility**        | `uv.lock` pins every transitive dep; pinned base images; `docker compose up` produces the same env everywhere |
| **Portability**            | Same image runs locally (kind), in EKS, or any K8s cluster               |
| **Testability**            | `backend/deployments/tests.py` with mocked K8s client                    |
| **Observability**          | The dashboard itself is an observability tool                            |

## Quick start (local kind cluster — no AWS needed)

This is the recommended path for graders or anyone without Penn Labs cloud
access. Brings up a real Kubernetes cluster inside a Docker container, loads
fake-but-realistic Deployments, and runs the dashboard against them.

### Prerequisites

- Docker Desktop (running)
- `kubectl`, `kind`, Node.js 18+, `uv`
  ```bash
  brew install kubectl kind node uv
  ```

`uv` manages the backend's Python dependencies. You don't need to install
Python yourself — `uv sync` reads `requires-python` from
`backend/pyproject.toml` and fetches a matching interpreter if your system
doesn't already have one.

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
uv sync                                   # creates .venv from uv.lock
uv run python manage.py migrate           # creates the auth database
uv run python manage.py runserver &
cd ..

# 4. Frontend
cd frontend
npm install
npm start
```

Or just `./dev.sh`, which does all of the above (including `migrate`) and
prints which cluster it's about to read.

Open <http://localhost:3000> — always port 3000, never 8000 directly, because
the dev server proxies `/api` through to Django to keep the OAuth flow
same-origin. Sign in with your PennKey, and you should see three product cards:
`penn-clubs` (green), `ohq` (green), `penn-courses` (red — the broken one,
demonstrating the degraded-health UI). Click in to see pods and ReplicaSet
history.

If you get "You don't have access yet", your Penn Labs account isn't a team
lead — see [Authentication](#authentication).

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
uv run python manage.py test
# Ran 23 tests in 0.038s — OK
```

`uv run` syncs the environment against `uv.lock` before executing, so you
never run tests against a stale set of packages.

The tests mock the Kubernetes client entirely, so they don't need a cluster.
They verify view logic (label-based product grouping, dict shaping for the JSON
API, 404 handling, rollback input validation) and access control: that anonymous
users and signed-in non-leads are refused, that a rollback is rejected *before*
the cluster is touched, and that the mapping from Platform permissions to lead
status grants and revokes correctly.

## Authentication

Sign-in is Penn Labs SSO, via [`django-labs-accounts`][dla] (DLA) — the same
client library Penn Clubs, OHQ and Penn Mobile use. **Access is currently
limited to team leads**, plus any pennkey named in `DASHBOARD_ALLOWED_USERS`.

Signing in is the **first** thing a visitor sees. Hitting `dashboard.pennlabs.org`
with no session redirects straight to Platform rather than showing a "sign in"
button, which is what Platform's own frontend does — `withAuth` in its
`frontend/utils/auth.tsx` redirects to `/accounts/login/?next=…` the moment
`/accounts/me/` comes back non-ok. Platform does that server-side in
`getServerSideProps`; this app is a static bundle behind nginx, so `AuthGate.tsx`
does the equivalent as soon as `/api/me/` answers. The one case that does *not*
auto-redirect is a **failed** sign-in (`?auth_error=…`), which would otherwise
loop — that renders an explanation and a manual "Try again".

### The flow

```
browser                    this app                     platform.pennlabs.org
   │                          │                                   │
   │ GET /api/accounts/login/ │                                   │
   ├─────────────────────────▶│                                   │
   │◀──── 302 ────────────────┤   /accounts/authorize/            │
   ├──────────────────────────────────────────────────────────────▶│
   │                          │           (PennKey / Shibboleth)  │
   │◀──── 302 back to /api/accounts/callback/?code=… ─────────────┤
   ├─────────────────────────▶│  exchange code at /accounts/token/│
   │                          ├──────────────────────────────────▶│
   │                          │  POST /accounts/introspect/       │
   │                          ├──────────────────────────────────▶│
   │                          │◀─ user: pennkey, name, email,     │
   │                          │       groups, user_permissions ───┤
   │◀──── 302 to / (session cookie set) ──────────────────────────┤
```

DLA's views are mounted at **`/api/accounts/`** rather than `/accounts/`. That's
deliberate: the production ingress already routes `/api` to Django (see
`k8s/main.ts`), so no extra ingress rule is needed, and `/api/accounts/callback/`
is the exact path Penn Labs' shared development OAuth client is registered
against.

### Who counts as a team lead

We don't keep our own list of pennkeys. Penn Labs already tracks this, and we
read it:

1. [`pennlabs/infrastructure`][infra]`/docker/team-sync` runs on a cron. Every
   GitHub team in the org whose slug ends in **`-leads`** is a lead team, and
   `<x>-leads` maps to the permission codename `<x>_admin` (dashes become
   underscores) — so `penn-clubs-leads` yields `penn_clubs_admin`. Members of
   the **`Directors`** team receive every such codename.
2. team-sync POSTs `{pennkey: [codenames]}` to Platform's
   `/accounts/productadmin/`, which materializes them as Django permissions.
3. Platform reports them back to us in the `user_permissions` field of the
   introspection response.

Because step 1 only ever issues `*_admin` codenames to lead teams and to
Directors, **"holds at least one `*_admin` permission" is exactly equivalent to
"is a lead of some team, or a Director"** (`deployments/backends.py`). It needs no
new GitHub team and no change to Platform. Lead status is re-evaluated on
**every** login, so someone who rotates off a team loses access next time they
sign in; `SESSION_COOKIE_AGE` (12h) bounds how long an already-issued session
outlives the change.

### Explicitly allowed pennkeys

`DASHBOARD_ALLOWED_USERS` (in `dashboard/settings/base.py`, overridable as a
comma-separated env var; defaults to `chenstan`) always has access, regardless of
permissions. It is additive — it never removes the lead rule — and matching is
case-insensitive. Two cases need it, and neither is a corner case:

- **Whoever operates this dashboard without leading a product team.** Step 1 only
  issues codenames to people who are *both* in a `*-leads` GitHub team *and*
  listed in team-sync's `roster.yaml`, so a DevOps maintainer holds no `*_admin`
  at all and would be locked out of the tool they run.
- **A Platform lead.** Platform's `ProductAdminView` special-cases the
  `platform_admin` slug: it sets `is_superuser` on the Platform-side user and
  `continue`s *before* creating a `Permission`. So `platform_admin` never comes
  back from introspection, and introspection doesn't expose `is_staff` /
  `is_superuser` either (see Platform's `UserSerializer.Meta.fields`) — there is
  nothing for the `*_admin` test to match. A Platform lead who leads no other
  product is refused without this. Directors are unaffected, because team-sync
  hands them every *other* product codename too.

Enforcement is server-side: `IsTeamLead` is the project-wide default DRF
permission, so every endpoint is closed unless it explicitly opts out. Only
`/api/health/` (liveness probes) and `/api/me/` (so the SPA can discover whether
you're signed in) are public. `AuthGate.tsx` is a UX layer on top, not the
boundary.

### Widening access later

Create a `dashboard-leads` team in the GitHub org. team-sync will start issuing
`dashboard_admin`, which the existing check already matches — no code change.

### Local development

Logging in locally does a real OAuth round-trip against
`platform-dev.pennlabs.org` using Penn Labs' shared development client
(configured in `dashboard/settings/development.py`). There is no auth-bypass
switch, so you need network access and a Penn Labs account on platform-dev.

⚠️ **Locally you are not yourself.** The shared development client authenticates
everyone as platform-dev's shared test account — `engineering`
(`engineering@upenn.edu`, pennid 1000) — not your own PennKey. Your real pennkey
only comes back from *production* Platform. So an allowlist of real pennkeys can
never match locally, and every local login would otherwise land on "You don't
have access yet". `development.py` therefore appends `engineering` to
`DASHBOARD_ALLOWED_USERS`. That module is never loaded in production, so the
shared test account cannot reach the real dashboard.

If a local login lands on "You don't have access yet", check which user you
actually became before assuming the OAuth flow is broken:

```bash
cd backend && sqlite3 db.sqlite3 'SELECT id, username, is_staff FROM auth_user;'
```

### Before this can run in production

⚠️ **Someone on Platform must register the OAuth client.** This is the one step
that cannot be done from this repo:

- register `https://dashboard.pennlabs.org/api/accounts/callback/` as a redirect
  URI, with scopes `read` and `introspection`
- put the issued credentials in Vault as `LABS_CLIENT_ID` / `LABS_CLIENT_SECRET`
  in the `dashboard` secret, alongside a `SECRET_KEY`

`dashboard.settings.production` refuses to start without `SECRET_KEY`, since it
signs session cookies.

Note the backend runs a **single replica** (`k8s/main.ts`). Auth state lives in a
SQLite file inside the container, so a session minted on one pod would mean
nothing on another. The file is ephemeral by design — Platform is the source of
truth for identity and lead status, so a pod restart just means users silently
re-authenticate through their existing SSO session. Moving to Postgres is what
would let the API scale out again.

[dla]: https://github.com/pennlabs/django-labs-accounts
[infra]: https://github.com/pennlabs/infrastructure

## Project structure

```
backend/
├── Dockerfile                       # multi-stage uv build
├── pyproject.toml                   # dependency declarations (uv)
├── uv.lock                          # fully-pinned resolution — commit this
├── manage.py
├── dashboard/                       # Django project
│   ├── settings/
│   │   ├── base.py                  # shared; SQLite for auth only, DLA config
│   │   ├── development.py           # local: ~/.kube/config, platform-dev OAuth
│   │   └── production.py            # in-cluster: ServiceAccount token, real OAuth
│   └── urls.py                      # mounts DLA at /api/accounts/
└── deployments/                     # the actual app
    ├── k8s_client.py                # all calls to the K8s API live here
    ├── backends.py                  # auth backend: who counts as a team lead
    ├── permissions.py               # IsTeamLead — the project-wide default
    ├── views.py                     # thin DRF views, no business logic
    ├── urls.py                      # routes keyed by (namespace, name)
    └── tests.py                     # unit tests with mocked K8s client

frontend/
├── Dockerfile                       # node build → nginx serve (also proxies /api)
└── src/
    ├── setupProxy.js                # dev-only: /api → Django, keeps OAuth same-origin
    ├── api/                         # fetch wrappers (+ CSRF header)
    ├── hooks/                       # React Query hooks (auto-refetch), useAuth
    ├── pages/                       # Dashboard, ProductDetail, DeploymentDetail
    ├── components/                  # AuthGate, HealthBadge, PodStatusList, ...
    └── types/                       # TypeScript shapes mirroring the API

k8s/
├── main.ts                          # CDK8s / Kittyhawk chart
├── package.json                     # `npm run build` synthesizes YAML to dist/
├── yarn.lock                        # pins cdk8s/constructs — CI needs this
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

## RBAC: least privilege in the cluster

Running inside the cluster, the backend pod authenticates as a ServiceAccount,
which by default has **zero** API permissions — without a role, every `list`
call 403s and the dashboard renders empty. `k8s/main.ts` declares the narrowest
ClusterRole that makes it work:

- `get`, `list`, `watch` on **deployments** and **replicasets** (apps/v1)
- `get`, `list`, `watch` on **pods** (core/v1)
- `patch` on **deployments** only (the rollback button)

No write access on pods or replicasets. No access to Secrets, ConfigMaps,
Services, or anything else. A bug or an exploit in the dashboard cannot delete
or modify any other workload in the cluster.

Two details worth knowing:

- The ServiceAccount, ClusterRole and ClusterRoleBinding are declared **in the
  chart**, not as a separate hand-written YAML file, so CI applies them with
  everything else. A standalone `rbac.yaml` would never be applied, since the
  deploy step only applies `k8s/dist/`.
- We do **not** use kittyhawk's `createServiceAccount: true`. It is broken —
  `application/base.js` passes the account down as `serviceAccountName` (a
  string) while `deployment.js` only emits that field when `props.serviceAccount`
  (an object) is set, so it creates a ServiceAccount and never attaches it, and
  the pod silently runs as `default`. It also annotates the account for IRSA,
  which expects a matching IAM role; we don't need one, because this backend
  calls the Kubernetes API, not any AWS API.

## Synthesizing the production manifests

```bash
cd k8s
yarn install --frozen-lockfile
RELEASE_NAME=dashboard GIT_SHA=$(git rev-parse HEAD) AWS_ACCOUNT_ID=<acct> yarn build
# YAML appears in k8s/dist/
```

All three environment variables are required. `RELEASE_NAME` in particular is
not optional: kittyhawk reads it to set `app.kubernetes.io/part-of`, which names
every resource and is what `kubectl apply --prune` selects on — omit it and you
get `undefined_release-*` names. `GIT_SHA` becomes the image tag.

Use **yarn**, not npm: `cdk8s` and `constructs` are pinned to exact versions with
a `resolutions` block, because kittyhawk's own caret ranges otherwise resolve to
newer copies that fail to compile against ours. `yarn.lock` is committed and CI
installs with `--frozen-lockfile`.

Inspect `dist/dashboard.k8s.yaml` to see exactly what deploys — 11 objects,
including the ServiceAccount and RBAC.

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
- **Postgres instead of SQLite** — auth state currently lives in a SQLite file
  inside the container, which is why the API runs a single replica. Swapping in
  Postgres (via `DATABASE_URL`, the way Platform and Penn Clubs do it) would let
  it scale out again. See [Authentication](#authentication).
- **Wider access than team leads** — the dashboard is deliberately restricted to
  leads for now. A `dashboard-leads` GitHub team would widen it without a code
  change.
- **Alerts** — turn the polling-based dashboard into push-based notifications
  when a deployment becomes unhealthy.
- **Multi-cluster support** — currently the backend reads one kubeconfig
  context at a time. Adding a context switcher would let one dashboard span
  staging + production.

## License

MIT.
