# Multi-stage build for the Django API.
#
# Stage 1 installs build-time deps (only needed if any wheel needs gcc) and
# resolves all Python packages. Stage 2 copies just the installed packages
# and the application code into a slim base, so the final image doesn't ship
# pip caches, build tools, or test files.

# ----- Build stage --------------------------------------------------------
FROM python:3.13-slim AS build
WORKDIR /app

# Disable bytecode + buffer flushing -> friendlier logs in container output.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ----- Runtime stage ------------------------------------------------------
FROM python:3.13-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=dashboard.settings.production

COPY --from=build /install /usr/local
COPY . .

EXPOSE 8000
# 2 gunicorn workers is fine -- the app is I/O bound (waiting on the K8s API).
CMD ["gunicorn", "dashboard.wsgi", "--bind", "0.0.0.0:8000", "--workers", "2"]
