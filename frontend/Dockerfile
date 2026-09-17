# Multi-stage build: Node builds the static assets, Nginx serves them.
# Build from the REPO ROOT so it's consistent with backend/Dockerfile:
#   docker build -f frontend/Dockerfile -t <tag> .
#
# No VITE_API_URL or similar build-time API URL is set on purpose — the
# frontend's fetch() calls all use relative paths and rely on being served
# from the same origin as the API via the ALB's path-based routing (see
# infrastructure/terraform README "Architecture overview"). Don't add one
# without also reworking that routing decision.

FROM node:22-slim AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
