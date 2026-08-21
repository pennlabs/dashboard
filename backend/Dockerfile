# Multi-stage build for the Django API.
#
# Stage 1 resolves and installs all Python packages with uv, into a virtualenv
# at /app/.venv. Stage 2 copies just that venv and the application code into a
# slim base, so the final image doesn't ship uv itself, its download cache, or
# any build tools.
#
# Dependencies come from pyproject.toml + uv.lock. `uv sync --frozen` installs
# the exact pinned versions from the lockfile and fails if it has drifted from
# pyproject.toml, so an image build can never silently resolve something new.

# ----- Build stage --------------------------------------------------------
FROM python:3.13-slim AS build
WORKDIR /app

# uv ships as a single static binary, so we copy it out of its published image
# rather than pip-installing it. Pinned for the same reason the base image is.
COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Copy packages into the venv instead of hardlinking them to uv's cache --
    # the cache lives in a build mount that won't exist in the runtime stage.
    UV_LINK_MODE=copy \
    # The base image already has the interpreter we asked for; never fetch one.
    UV_PYTHON_DOWNLOADS=never

# Only the dependency manifests, so this layer stays cached until deps actually
# change -- editing application code doesn't trigger a reinstall.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ----- Runtime stage ------------------------------------------------------
FROM python:3.13-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=dashboard.settings.production \
    # Putting the venv first on PATH makes bare `python` and `gunicorn` resolve
    # to it, so CMD and docker-compose's `command:` need no uv-specific prefix.
    PATH="/app/.venv/bin:$PATH"

COPY --from=build /app/.venv /app/.venv
COPY . .

EXPOSE 8000
# 2 gunicorn workers is fine -- the app is I/O bound (waiting on the K8s API).
CMD ["gunicorn", "dashboard.wsgi", "--bind", "0.0.0.0:8000", "--workers", "2"]
