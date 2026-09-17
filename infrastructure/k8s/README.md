# Local Kubernetes deployment (kind)

Runs the full stack — Postgres/pgvector, Redis, Kafka, backend API, telemetry
consumer, simulator, and frontend — in a local [kind](https://kind.sigs.k8s.io/)
cluster.

## Prerequisites

```
brew install kind        # if not already installed
```

Docker and `kubectl` are assumed to already be available.

## One-shot deploy

```
infrastructure/k8s/deploy-local.sh
```

This creates the cluster (if it doesn't exist), builds the `backend` and
`frontend` images, loads them into kind, applies all manifests, runs
migrations, and restarts the app workloads. Re-running it is safe — it
reuses the existing cluster and picks up new code.

Open the app at **http://localhost:8080** (mapped from the frontend's
NodePort 30080 via `kind-config.yaml`'s `extraPortMappings`).

## Secrets

`secret.yaml` is gitignored. The script copies `secret.example.yaml` to
`secret.yaml` automatically on first run with placeholder values — good
enough for a local smoke test, but edit it with real `JWT_SECRET_KEY`,
`AI_API_KEY`, and `VOYAGE_API_KEY` values if you want the AI agent or
document search features to work:

```
kubectl apply -f infrastructure/k8s/secret.yaml   # after editing
kubectl rollout restart deployment/backend -n robot-fleet
```

## Iterating on code changes

The images are loaded into kind directly (no registry), so after editing
code:

```
docker build -f backend/Dockerfile -t robot-fleet-backend:local .
kind load docker-image robot-fleet-backend:local --name robot-fleet
kubectl rollout restart deployment/backend -n robot-fleet
```

(swap in `frontend/Dockerfile` / `robot-fleet-frontend:local` / `deployment/frontend`
for frontend changes). Or just re-run `deploy-local.sh`, which does all of this.

## Useful commands

```
kubectl get pods -n robot-fleet
kubectl logs -n robot-fleet -l app=backend -f
kubectl port-forward -n robot-fleet svc/backend 8000:8000   # bypass the frontend proxy
```

## Re-running migrations

Migrations run as a Kubernetes `Job`, which can't be re-applied in place —
delete it first:

```
kubectl delete job/migrate -n robot-fleet --ignore-not-found
kubectl apply -f infrastructure/k8s/migrate-job.yaml
```

## Tearing down

```
kind delete cluster --name robot-fleet
```

## What's here

| File | Purpose |
|---|---|
| `namespace.yaml` | Dedicated `robot-fleet` namespace |
| `configmap.yaml` | Non-secret env vars |
| `secret.example.yaml` | Template for secrets (copy to `secret.yaml`, never commit that copy) |
| `postgres.yaml` | Postgres/pgvector StatefulSet + headless Service + PVC |
| `redis.yaml` | Redis Deployment + Service |
| `kafka.yaml` | Single-broker Kafka (KRaft mode) Deployment + Service |
| `migrate-job.yaml` | One-shot `alembic upgrade head` Job |
| `backend.yaml` | API Deployment (2 replicas) + Service |
| `telemetry-consumer.yaml` | Kafka → Postgres consumer Deployment (1 replica) |
| `simulator.yaml` | Optional fake-telemetry generator, demo only |
| `frontend.yaml` | Static frontend + nginx reverse proxy, Deployment + NodePort Service |
| `kustomization.yaml` | Ties the above together for `kubectl apply -k` |
| `kind-config.yaml` | kind cluster config with the NodePort → host port mapping |
| `deploy-local.sh` | Build, load, apply, migrate, in one command |

Ingress (e.g. `ingress-nginx`) isn't set up — the NodePort + kind port mapping
is simpler for local use. Add an Ingress if you need path-based routing or
TLS termination in front of the cluster.
