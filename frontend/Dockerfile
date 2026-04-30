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
# REACT_APP_* env vars are baked in at build time; default to relative URLs
# so this image works behind any reverse proxy.
ARG REACT_APP_API_BASE_URL=""
ENV REACT_APP_API_BASE_URL=$REACT_APP_API_BASE_URL
RUN npm run build

# ----- Serve stage --------------------------------------------------------
FROM nginx:1.27-alpine
# React Router uses client-side routing, so any path that isn't a real file
# needs to fall back to index.html. The default nginx config 404s instead.
RUN printf 'server {\n\
  listen 80;\n\
  root /usr/share/nginx/html;\n\
  location / {\n\
    try_files $uri /index.html;\n\
  }\n\
}\n' > /etc/nginx/conf.d/default.conf

COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
