#!/usr/bin/env bash
# Build the app images and deploy the full stack to a local kind cluster.
# Safe to re-run: creates the cluster only if missing, and re-applies
# manifests idempotently. Re-runs the migrate Job on every invocation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLUSTER_NAME="robot-fleet"

cd "$REPO_ROOT"

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "==> Creating kind cluster '$CLUSTER_NAME'"
  kind create cluster --config infrastructure/k8s/kind-config.yaml
else
  echo "==> kind cluster '$CLUSTER_NAME' already exists, reusing it"
fi

if [ ! -f infrastructure/k8s/secret.yaml ]; then
  echo "==> infrastructure/k8s/secret.yaml not found — copying from secret.example.yaml"
  echo "    Edit it with real values (JWT_SECRET_KEY, AI_API_KEY, VOYAGE_API_KEY) before using this for anything but a quick local smoke test."
  cp infrastructure/k8s/secret.example.yaml infrastructure/k8s/secret.yaml
fi

echo "==> Building images"
docker build -f backend/Dockerfile -t robot-fleet-backend:local .
docker build -f frontend/Dockerfile -t robot-fleet-frontend:local .

echo "==> Loading images into kind"
kind load docker-image robot-fleet-backend:local robot-fleet-frontend:local --name "$CLUSTER_NAME"

echo "==> Applying manifests"
kubectl apply -k infrastructure/k8s/

echo "==> Waiting for infra to be ready"
kubectl -n robot-fleet rollout status statefulset/postgres --timeout=120s
kubectl -n robot-fleet rollout status deployment/redis --timeout=120s
kubectl -n robot-fleet rollout status deployment/kafka --timeout=120s

echo "==> Running database migrations"
kubectl delete job/migrate -n robot-fleet --ignore-not-found
kubectl apply -f infrastructure/k8s/migrate-job.yaml
kubectl -n robot-fleet wait --for=condition=complete job/migrate --timeout=120s

echo "==> Restarting app workloads (loads any new image, retries post-migration)"
kubectl -n robot-fleet rollout restart deployment/backend deployment/telemetry-consumer deployment/simulator deployment/frontend
kubectl -n robot-fleet rollout status deployment/backend --timeout=120s
kubectl -n robot-fleet rollout status deployment/frontend --timeout=120s

echo
echo "==> Done. Frontend: http://localhost:8080  (backend health: http://localhost:8080/health)"
echo "    kubectl get pods -n robot-fleet"
echo "    kind delete cluster --name $CLUSTER_NAME   # tear down"
