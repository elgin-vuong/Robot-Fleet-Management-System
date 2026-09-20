FROM node:22-slim AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine

# The published nginx:1.27-alpine layer can lag Alpine's own package repo by
# days after a CVE fix lands there (observed: CVE-2026-31789 in
# libssl3/libcrypto3, fixed upstream in Alpine but not yet in this image tag
# as of this Dockerfile). `apk upgrade` pulls whatever's currently patched
# in Alpine's repos at build time rather than waiting on a Docker Hub
# rebuild — cheap (one more layer, same base) and closes exactly this class
# of gap. docker.yml's Trivy scan step is what actually catches it if this
# ever regresses.
RUN apk upgrade --no-cache

COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

# nginx:alpine's entrypoint runs envsubst over /etc/nginx/templates/*.template
# into /etc/nginx/conf.d/ automatically on container start.
ENV BACKEND_HOST=backend
ENV BACKEND_PORT=8000

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -q -O- http://127.0.0.1/healthz || exit 1
