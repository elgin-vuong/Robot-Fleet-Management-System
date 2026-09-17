FROM node:22-slim AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

# nginx:alpine's entrypoint runs envsubst over /etc/nginx/templates/*.template
# into /etc/nginx/conf.d/ automatically on container start.
ENV BACKEND_HOST=backend
ENV BACKEND_PORT=8000

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -q -O- http://127.0.0.1/healthz || exit 1
