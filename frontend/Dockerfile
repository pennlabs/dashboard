# Multi-stage build:
#   1. Compile the React app with Node.
#   2. Serve the static bundle with nginx.
#
# The final image has no Node, no source code, and no devDependencies -- just
# nginx + the compiled bundle. Tiny (~25 MB) and fast to start.

# ----- Build stage --------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

# Copy lockfile first so Docker can cache the npm install layer separately
# from the source code (changing a .tsx file shouldn't trigger a re-install).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# REACT_APP_* env vars are baked in at build time. Leave this empty: the app
# should call /api on its own origin, which nginx forwards to the backend below.
# Same-origin is what makes the OAuth session and CSRF cookies work.
ARG REACT_APP_API_BASE_URL=""
ENV REACT_APP_API_BASE_URL=$REACT_APP_API_BASE_URL
RUN npm run build

# ----- Serve stage --------------------------------------------------------
FROM nginx:1.27-alpine
# Two rules:
#   /api -> the Django service. Needed for the OAuth redirect chain (the browser
#           navigates to /api/accounts/login/ and returns to
#           /api/accounts/callback/) to stay on one origin. In the production
#           cluster the ingress does this instead, per k8s/main.ts.
#   /    -> React Router uses client-side routing, so any path that isn't a real
#           file falls back to index.html. The default config 404s instead.
#
# API_UPSTREAM is templated at container start (nginx:alpine runs envsubst over
# /etc/nginx/templates/*.template) so docker-compose can point it at its own
# service name without rebuilding the image.
ENV API_UPSTREAM=http://backend:8000
RUN mkdir -p /etc/nginx/templates && printf 'server {\n\
  listen 80;\n\
  root /usr/share/nginx/html;\n\
  location /api/ {\n\
    proxy_pass ${API_UPSTREAM};\n\
    proxy_set_header Host $host;\n\
    proxy_set_header X-Real-IP $remote_addr;\n\
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
    proxy_set_header X-Forwarded-Proto $scheme;\n\
  }\n\
  location / {\n\
    try_files $uri /index.html;\n\
  }\n\
}\n' > /etc/nginx/templates/default.conf.template \
 && rm -f /etc/nginx/conf.d/default.conf

COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
