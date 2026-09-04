#!/usr/bin/env bash
#
# Start the dashboard locally: Django API + React dev server.
#
#   ./dev.sh                  # both services
#   ./dev.sh --backend-only   # just the API
#   ./dev.sh --frontend-only  # just the SPA
#
# The backend reads whatever cluster your kubeconfig currently points at. The
# kubeconfig's exec block supplies its own AWS_PROFILE, so you do NOT need to
# export one here -- see the banner this script prints for the live target.
#
# Ctrl+C stops everything.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

RUN_BACKEND=1
RUN_FRONTEND=1

while [ $# -gt 0 ]; do
  case "$1" in
    --backend-only)  RUN_FRONTEND=0 ;;
    --frontend-only) RUN_BACKEND=0 ;;
    -h|--help)       sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

# ---------------------------------------------------------------- formatting
if [ -t 1 ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; BLUE=$'\033[34m'; CYAN=$'\033[36m'; RESET=$'\033[0m'
else
  BOLD=''; DIM=''; RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; RESET=''
fi

info()  { echo "${DIM}==>${RESET} $*"; }
ok()    { echo "${GREEN}✓${RESET} $*"; }
warn()  { echo "${YELLOW}!${RESET} $*"; }
die()   { echo "${RED}✗${RESET} $*" >&2; exit 1; }

# ------------------------------------------------------------------ preflight
need() { command -v "$1" >/dev/null 2>&1 || die "$1 is not installed (brew install $2)"; }

if [ "$RUN_BACKEND" = 1 ]; then need uv uv; fi
if [ "$RUN_FRONTEND" = 1 ]; then need npm node; fi

# Prints the listening pid, or nothing. Always exits 0 -- lsof returns
# non-zero for "no match", which under `set -o pipefail` would abort the script.
port_pid() { lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null | head -1 || true; }

check_port() {
  local port="$1" label="$2" pid
  pid="$(port_pid "$port")"
  if [ -n "$pid" ]; then
    die "port $port ($label) is already in use by pid $pid — \`kill $pid\` or set ${label}_PORT"
  fi
}

if [ "$RUN_BACKEND" = 1 ];  then check_port "$BACKEND_PORT" BACKEND; fi
if [ "$RUN_FRONTEND" = 1 ]; then check_port "$FRONTEND_PORT" FRONTEND; fi

# Show which cluster we're about to read. This is the one thing worth seeing
# every single time: dev settings point at your *current* kubectl context, and
# the rollback endpoint is unauthenticated.
if [ "$RUN_BACKEND" = 1 ]; then
  if ! command -v kubectl >/dev/null 2>&1; then
    warn "kubectl not found — skipping cluster preflight"
  elif ! ctx="$(kubectl config current-context 2>/dev/null)" || [ -z "$ctx" ]; then
    die "no current kubectl context — the backend has no cluster to read"
  else
    if ! kubectl cluster-info >/dev/null 2>&1; then
      die "cannot reach cluster '${ctx}' — check your credentials, then retry"
    fi
    n_deploys="$(kubectl get deployments -A \
      -l app.kubernetes.io/managed-by=kittyhawk \
      --no-headers 2>/dev/null | wc -l | tr -d ' ' || true)"
    : "${n_deploys:=0}"
    echo
    echo "  ${BOLD}cluster${RESET}  ${CYAN}${ctx}${RESET}"
    echo "  ${BOLD}visible${RESET}  ${n_deploys} kittyhawk-labeled deployments"
    case "$ctx" in
      *prod*) echo "  ${BOLD}${YELLOW}note${RESET}     live production — the rollback button really patches Deployments" ;;
    esac
    echo
    if [ "$n_deploys" = 0 ]; then
      warn "no matching deployments — the dashboard will render empty"
    fi
  fi
fi

if [ "$RUN_FRONTEND" = 1 ] && [ ! -d "$ROOT/frontend/node_modules" ]; then
  info "installing frontend dependencies (first run)"
  ( cd "$ROOT/frontend" && npm install )
fi

# -------------------------------------------------------------------- cleanup
PIDS=""

cleanup() {
  trap - INT TERM EXIT
  echo
  info "shutting down"
  for pid in $PIDS; do
    kill "$pid" 2>/dev/null || true
  done
  # Sweep anything still holding the ports (autoreloader children, nodemon, ...)
  for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    pid="$(port_pid "$port" || true)"
    if [ -n "$pid" ]; then kill "$pid" 2>/dev/null || true; fi
  done
  wait 2>/dev/null || true
  ok "stopped"
}
trap cleanup INT TERM EXIT

# Prefix each service's output so interleaved logs stay readable. awk's
# fflush() keeps lines appearing immediately instead of sitting in a buffer.
prefix() {
  awk -v tag="$1" '{ printf "%s %s\n", tag, $0; fflush() }'
}

# --------------------------------------------------------------------- backend
if [ "$RUN_BACKEND" = 1 ]; then
  info "starting backend on :${BACKEND_PORT}"
  (
    cd "$ROOT/backend"
    # Unset so a stray conda/venv activation doesn't make `uv run` warn.
    unset VIRTUAL_ENV
    exec uv run python manage.py runserver "127.0.0.1:${BACKEND_PORT}" 2>&1
  ) | prefix "${BLUE}[api]${RESET}" &
  PIDS="$PIDS $!"

  # Wait for the liveness probe before starting the SPA, so the first page
  # load doesn't race the server and show a fetch error.
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/health/" >/dev/null 2>&1; then
      ok "backend ready — http://localhost:${BACKEND_PORT}/api/health/"
      break
    fi
    sleep 0.5
  done
fi

# -------------------------------------------------------------------- frontend
if [ "$RUN_FRONTEND" = 1 ]; then
  info "starting frontend on :${FRONTEND_PORT}"
  (
    cd "$ROOT/frontend"
    export PORT="$FRONTEND_PORT"
    export REACT_APP_API_BASE_URL="http://localhost:${BACKEND_PORT}"
    export BROWSER="${BROWSER:-none}"
    exec npm start 2>&1
  ) | prefix "${CYAN}[web]${RESET}" &
  PIDS="$PIDS $!"

  echo
  ok "dashboard → ${BOLD}http://localhost:${FRONTEND_PORT}${RESET}"
  echo "  ${DIM}Ctrl+C to stop both services${RESET}"
  echo
fi

wait
