# Robot Fleet Management System — AWS Infrastructure

Terraform for deploying the Robot Fleet Management System to AWS. This
document assumes you've read the top-level repo but never touched this
`infrastructure/terraform/` directory before.

## Architecture overview

```
Internet
   │
   ▼
Route 53 (optional, only if domain_name is set)
   │
   ▼
ACM certificate (optional, only if domain_name is set)
   │
   ▼
Application Load Balancer  (public subnets, 2 AZs)
   │
   ├─ path /robots*, /auth*, /agent*, /ws*, /documents*, /incidents*, /health
   │        │
   │        ▼
   │  backend target group ──▶ ECS Fargate: backend-api service (FastAPI)
   │
   └─ path /* (default)
            │
            ▼
      frontend target group ──▶ ECS Fargate: frontend service (Nginx + React build)

ECS Fargate cluster (private APPLICATION subnets, 2 AZs)
   ├─ backend-api          (behind ALB)
   ├─ frontend             (behind ALB)
   ├─ telemetry-consumer   (no ALB — reads Kafka, writes Postgres + Redis pub/sub)
   └─ simulator            (no ALB — generates demo telemetry, publishes to Kafka)
        ↑ telemetry-consumer and simulator only exist when enable_kafka = true —
          see "Kafka / event streaming" below.

Private DATA subnets (2 AZs — no route to the internet at all, not even via NAT)
   ├─ RDS PostgreSQL   (pgvector-enabled engine, for document search embeddings)
   ├─ ElastiCache Redis (cache, agent confirmations/history, rate limiting,
   │                     Kafka→WebSocket pub/sub bridge)
   └─ MSK Kafka         (only when enable_kafka = true)

Cross-cutting
   ├─ S3            — exports/telemetry/document artifacts (private, versioned, encrypted)
   ├─ Secrets Manager — DB credentials, Redis AUTH token, JWT secret, AI/Voyage API keys
   ├─ ECR           — backend image (API + both workers), frontend image
   ├─ CloudWatch    — log groups per service, alarms, SNS topic
   └─ IAM           — task execution role, backend/worker task roles, GitHub OIDC deploy role
```

**Why one ALB with path-based routing, not a separate frontend origin
(e.g. S3 + CloudFront)?** The React app's `fetch()` calls all use relative
paths (`/robots`, `/auth/login`, `/agent/chat`, `/ws/robots`) and assume
same-origin — there's no `VITE_API_URL` or similar anywhere in the
frontend code. Path-based ALB routing reproduces that same-origin
assumption in production with **zero frontend code changes**, at the cost
of the frontend also having to run as an ECS service (a static host would
otherwise be cheaper). If you later add a CDN in front of this, put it in
front of the whole ALB (CloudFront can do path-based origin routing too),
not a separate S3 origin, to preserve the same-origin behavior.

## AWS service inventory

| Service | Purpose | Created by default? |
|---|---|---|
| VPC, subnets, IGW, NAT, route tables | Networking | Yes |
| Security Groups | Network-level access control | Yes |
| Application Load Balancer | Public HTTP(S) entry point | Yes |
| ECS Fargate (cluster, services, task defs) | Runs backend/frontend/workers | Yes |
| ECR | Container image storage | Yes |
| RDS PostgreSQL | Primary database (pgvector-enabled) | Yes |
| ElastiCache Redis | Cache, pub/sub, rate limiting | Yes |
| Amazon MSK | Kafka (telemetry event streaming) | **No** — `enable_kafka = false` by default |
| S3 | Exports / document / telemetry artifacts | Yes |
| Secrets Manager | Runtime secrets | Yes |
| CloudWatch (Logs, Alarms, SNS) | Observability | Yes |
| IAM (roles, OIDC provider) | Least-privilege access | Yes |
| Route 53, ACM | Custom domain + TLS | **No** — only if `domain_name` is set |

## Network topology

Three subnet tiers, each duplicated across `az_count` (default 2) Availability Zones:

- **Public subnets** — the ALB and NAT Gateway(s) live here. `map_public_ip_on_launch = true`. Routed to the internet via an Internet Gateway.
- **Private application subnets** — ECS Fargate tasks (backend, frontend, workers) live here. No public IPs. Outbound internet access (for ECR pulls, calling the Anthropic/Voyage AI APIs) goes through a NAT Gateway, per `nat_strategy`.
- **Private data subnets** — RDS, ElastiCache, and MSK live here. **No route to the internet at all**, not even via NAT. These are reachable only from the application subnets' security groups, on the specific ports each service needs (5432, 6379, 9092/9094). This is the strongest network-level guarantee in this stack: even a fully compromised backend task can't be used to exfiltrate data to an arbitrary internet host directly from the database tier, because the database tier has no route out.

## Terraform structure

```
infrastructure/terraform/
├── README.md                     (this file)
├── versions.tf, providers.tf     Terraform/provider setup
├── variables.tf, locals.tf       inputs and derived values
├── outputs.tf                    important resource identifiers
├── main.tf                       shared helper resources (random_id for S3 naming)
├── networking.tf, security.tf,   thin "wiring" files — each calls the
│ compute.tf, database.tf,        matching module in modules/
│ cache.tf, messaging.tf,
│ storage.tf, monitoring.tf
├── iam.tf, ecr.tf, secrets.tf,   implemented directly at root (NOT as
│ acm.tf                          modules) — see note below
├── terraform.tfvars.example      generic override template
├── environments/dev.tfvars       the dev environment's variable values
└── modules/
    ├── networking/   VPC, subnets, route tables, NAT
    ├── security/      all security groups (kept together since they
    │                  cross-reference each other heavily)
    ├── compute/       ECS cluster, ALB, task defs, services, log groups
    ├── database/      RDS PostgreSQL
    ├── cache/         ElastiCache Redis
    ├── messaging/     MSK (only instantiated when enable_kafka = true)
    ├── storage/       S3
    └── monitoring/    CloudWatch alarms + SNS topic
```

**Why aren't IAM, ECR, and Secrets Manager modules?** Every resource in
those three areas needs ARNs from several *other* modules (a Secrets
Manager secret needs the RDS password; an IAM policy needs the S3 bucket
ARN and the Secrets Manager ARNs; ECR repos are referenced by both compute
and iam.tf). Wrapping them in modules would mean passing most of the
root module's own state back into itself through module inputs, for no
real encapsulation benefit — so they're implemented directly at root,
exactly as the requested structure describes.

## Prerequisites

- Terraform >= 1.6.0 ([download](https://developer.hashicorp.com/terraform/downloads); this was built and validated against 1.9.8)
- An AWS account and credentials with sufficient permissions (see "Required AWS permissions" below) configured via any method the AWS provider supports (`aws configure`, environment variables, SSO, etc.)
- Docker, for building the backend/frontend images
- An AWS account is **not** required to run `terraform fmt`/`terraform validate` — only `plan`/`apply`/`destroy` need real credentials.

## Local setup (validate without touching AWS)

```bash
cd infrastructure/terraform
terraform fmt -recursive -check   # confirms formatting, changes nothing
terraform init -backend=false     # downloads providers only, no state backend
terraform validate                # confirms the config is internally consistent
```

All three of the above were run as part of building this stack and pass
clean with no AWS credentials configured.

## Terraform commands (once you have AWS credentials)

```bash
cd infrastructure/terraform
terraform init
terraform plan  -var-file=environments/dev.tfvars
terraform apply -var-file=environments/dev.tfvars
# ... later, to tear it down:
terraform destroy -var-file=environments/dev.tfvars
```

**Nothing in this repository ever runs `apply` or `destroy` automatically.**
Both are always a deliberate, human-run command.

## Remote state (recommended before a second person or CI touches this)

This configuration currently uses **local state** (a `terraform.tfstate`
file on whoever's machine runs `apply`) — fine for one developer
experimenting with `dev`, unsafe for a team or for staging/prod (two
people can silently overwrite each other's state, and the state file
contains sensitive values in plaintext on disk).

Before more than one person runs `apply`, bootstrap remote state as a
**separate, one-time step** (deliberately not automated by this
configuration, so a first `terraform init` here can never accidentally
create the very state infrastructure it depends on):

1. Create an S3 bucket (versioned, encrypted, public access blocked) to hold state files, and a DynamoDB table with a `LockID` (string) primary key for locking.
2. Uncomment the `backend "s3" { ... }` block at the bottom of `versions.tf` and fill in the bucket/table/region you created.
3. Run `terraform init` again — Terraform will offer to migrate your existing local state into the new backend.
4. Restrict IAM access to that S3 bucket/DynamoDB table to only the people/roles that should be able to run Terraform.

## Environment configuration

Everything environment-specific is a variable (`variables.tf`), with
values supplied via `-var-file`. `environments/dev.tfvars` is the only one
that exists today.

### Adding staging/prod later

1. Copy `environments/dev.tfvars` to `environments/staging.tfvars` (or `prod.tfvars`).
2. Change at minimum: `environment`, and the safety-relevant values — `db_multi_az = true`, `db_deletion_protection = true`, `db_skip_final_snapshot = false`, `nat_strategy = "one_per_az"`, `redis_replica_count >= 1`, `enable_container_insights = true` (in compute.tf's module call), real `domain_name`/`alarm_email`.
3. Run with `-var-file=environments/staging.tfvars`. Because `local.name_prefix` includes `environment`, this creates an entirely separate, non-overlapping set of resource names — safe to run alongside `dev` in the same AWS account, though separate AWS accounts per environment is the more common pattern at this stage of hardening (see "Future production hardening tasks").
4. Once more than one environment/person is applying, set up remote state (above) with a distinct state key per environment (e.g. `robot-fleet/staging/terraform.tfstate`).

## Deployment process (end to end, first time)

1. `terraform apply -var-file=environments/dev.tfvars` — creates everything **except working application containers** (ECR repos exist but are empty; ECS services will be created but their tasks will fail to start until an image exists at the tag you specified).
2. Build and push images — see "ECR image workflow" below.
3. Force a new deployment so ECS picks up the now-existing image: `aws ecs update-service --cluster <cluster> --service <service> --force-new-deployment` (get exact names from `terraform output`).
4. Populate the `AI_API_KEY` and `VOYAGE_API_KEY` secrets — see "Secrets management" below. Without this, the app runs fine; only the AI agent chat and document search features return `503`.
5. Run database migrations once — see the one-off task command below.
6. Visit `terraform output app_url`.

### Running Alembic migrations against RDS (one-off ECS task, not baked into every container boot)

Deliberately not run automatically on every container start — concurrent
task replicas racing to run migrations at once is a real hazard. Run it
once, manually, after each deployment that includes new migrations:

```bash
aws ecs run-task \
  --cluster $(terraform output -raw ecs_cluster_name) \
  --task-definition <backend-task-def-family> \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<app-subnet-ids>],securityGroups=[<backend-sg-id>]}" \
  --overrides '{"containerOverrides":[{"name":"backend","command":["python","-m","alembic","upgrade","head"]}]}'
```

## ECR image workflow

Both `backend/Dockerfile` and `frontend/Dockerfile` build **from the repo
root** (not from `backend/`/`frontend/`), since the backend's import paths
(`backend.app.main`, `backend.simulator.run`, ...) expect that layout:

```bash
# Authenticate Docker to ECR (once per session)
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

# Backend — ONE image serves the API, telemetry-consumer, and simulator
# task definitions (same image, different container `command`)
docker build -f backend/Dockerfile -t <account-id>.dkr.ecr.<region>.amazonaws.com/robot-fleet-dev-backend:<tag> .
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/robot-fleet-dev-backend:<tag>

# Frontend
docker build -f frontend/Dockerfile -t <account-id>.dkr.ecr.<region>.amazonaws.com/robot-fleet-dev-frontend:<tag> .
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/robot-fleet-dev-frontend:<tag>
```

**Image tags**: repos are `IMMUTABLE` — once a tag is pushed, it can't be
overwritten. Use a real identifier (a git SHA is the standard choice, e.g.
`git rev-parse --short HEAD`), not `latest`, for anything beyond quick
local experiments — `latest` is only the *default* in `variables.tf` to
make the very first `apply` simpler.

**Deploying a new image after it's pushed**: set `backend_image_tag`
and/or `frontend_image_tag` to the new tag and `terraform apply` again (the
ECS task definitions have `lifecycle.ignore_changes` on the task
definition itself specifically so CI can update the running service
without fighting Terraform on every plan — but changing the *tag variable*
and applying is still how Terraform-driven deploys work; a CI pipeline
would instead call `aws ecs register-task-definition` + `update-service`
directly, which is what the documented future GitHub Actions deploy step
does).

Both Dockerfiles were built and run locally against this repo's real
`docker-compose.yml` Postgres/Redis during development of this stack —
confirmed to boot, connect, and serve `/health` as `200` and an
unauthenticated `/robots` as `401` (proving both DB connectivity and
route registration actually work), not just "should work."

## Secrets management

All runtime secrets live in Secrets Manager, injected into ECS task
definitions by ARN — **never** as plain environment variables, never
baked into an image, never committed to source control.

| Secret | Populated by | Notes |
|---|---|---|
| `<prefix>/db-credentials` | Terraform (generated) | JSON: `username`, `password`, `host`, `port`, `dbname`, `url` |
| `<prefix>/redis-auth` | Terraform (generated) | Only exists if `redis_transit_encryption_enabled = true`. JSON: `auth_token`, `url` |
| `<prefix>/jwt-secret` | Terraform (generated) | Plain string, matches `backend/app/auth.py`'s `JWT_SECRET_KEY` |
| `<prefix>/ai-api-key` | **You, manually, after apply** | Starts as the placeholder string `REPLACE_ME` |
| `<prefix>/voyage-api-key` | **You, manually, after apply** | Starts as the placeholder string `REPLACE_ME` |

Populate the two manual ones after the first apply:

```bash
aws secretsmanager put-secret-value --secret-id $(terraform output -raw ai_api_key_secret_arn) --secret-string "sk-ant-..."
aws secretsmanager put-secret-value --secret-id $(terraform output -raw voyage_api_key_secret_arn) --secret-string "pa-..."
```

Then force a new ECS deployment so running tasks pick up the new secret
value (ECS resolves `secrets` only at task start, not live).
Terraform's `lifecycle.ignore_changes = [secret_string]` on these two
secrets means a later `terraform apply` will **never** overwrite whatever
value you put there.

## Cost considerations

This is a startup project — every one of these is a real, ongoing charge
whether or not the app is actually being used, and none of them are
disabled by pausing the app; only `terraform destroy` (or scaling to 0)
stops the charge.

| Resource | Cost driver | Dev default | To reduce/stop |
|---|---|---|---|
| **NAT Gateway** | ~$0.045/hr + ~$0.045/GB processed, *whether or not it's used* | 1 shared (`nat_strategy = "single"`) | `nat_strategy = "none"` if nothing needs outbound internet (breaks Anthropic/Voyage calls and ECR pulls without VPC endpoints — not recommended); otherwise this is close to the practical floor |
| **RDS** | Instance-hours + storage; Multi-AZ ~doubles it | `db.t4g.micro`, single-AZ, 20GB | `terraform destroy` when not in use, or stop the instance manually (still bills for storage) |
| **ElastiCache** | Node-hours | `cache.t4g.micro`, 1 node, no replicas | Same — destroy or accept the small always-on cost |
| **MSK** | Broker-hours + storage, *whether or not anything is published* | **Disabled** (`enable_kafka = false`) — a minimal 2×`kafka.t3.small` cluster is ~$60+/month before storage | Keep disabled for dev; only enable when you actually need a shared durable Kafka |
| **ALB** | ~$16-20/month base + LCU (load/connection/data usage) | 1 ALB, minimal traffic | Only real way to reduce is `terraform destroy` between working sessions |
| **ECS Fargate** | vCPU/memory-hours while tasks are RUNNING | Smallest sizes (0.25 vCPU/0.5GB), 1 task per service | Scale `desired_count` to 0 for services you're not using instead of destroying (keeps config, stops billing for that service) |
| **CloudWatch Logs** | Ingestion + storage, scales with log volume | 14-day retention | Lower `log_retention_days`; avoid `DEBUG`-level app logging in anything long-running |
| **Public IPv4 addresses** | ~$0.005/hr **per address**, since Feb 2024 — easy to miss | 1 (the NAT Gateway's EIP) | Fewer NAT Gateways = fewer public IPs; this is a newer AWS charge worth knowing about even outside this project |

**Rule of thumb for this stack in dev**, everything running, Kafka
disabled: comfortably under $100/month, with the NAT Gateway, RDS, and ALB
as the three largest fixed contributors regardless of traffic.

## Security considerations

- [x] No secret is ever hardcoded — all generated by Terraform (`random_password`) or supplied post-apply via Secrets Manager
- [x] RDS and ElastiCache are not publicly accessible (`publicly_accessible = false` / private subnet placement with no internet route)
- [x] MSK brokers (when enabled) are private, TLS-only for client-broker traffic
- [x] Security groups are least-privilege: each tier only accepts traffic from the specific tier that legitimately calls it (e.g. RDS only from backend/worker SGs, never from the ALB or the internet)
- [x] No long-lived AWS access keys anywhere — GitHub Actions uses OIDC federation
- [x] IAM roles are split by function (task execution vs. task runtime vs. CI/CD deploy), not one shared "does everything" role
- [x] S3 bucket blocks all public access, encrypted at rest, versioned
- [x] Redis and RDS credentials are per-environment, generated fresh, never shared across `dev`/`staging`/`prod`
- [ ] **Not yet done**: HTTPS is only enabled if you supply `domain_name` — dev defaults to plain HTTP on the ALB's own DNS name
- [ ] **Not yet done**: no WAF in front of the ALB
- [ ] **Not yet done**: MSK client authentication is network-isolation-only (no SASL/SCRAM or IAM auth) — see `modules/messaging/main.tf`
- [ ] **Not yet done**: no automated secret rotation (RDS/Secrets Manager support it; not configured here)

## Disaster recovery notes

- **RDS**: automated backups retained `db_backup_retention_days` (3 in dev). `db_skip_final_snapshot = true` in dev means destroying the instance takes **no** final snapshot — deliberate for a disposable dev environment, but flip to `false` before this ever holds data you can't regenerate.
- **ElastiCache**: no backup/snapshot configuration in this stack — Redis here holds only cache/session/rate-limit data that's fine to lose (nothing here is a system of record; if that changes, add `snapshot_retention_limit`).
- **S3**: versioning is on, so accidental overwrites/deletes are recoverable (subject to the lifecycle rule expiring noncurrent versions after 30 days).
- **Terraform state**: local state has no disaster recovery at all — this is the single biggest reason to set up remote state (above) before this matters to you.
- **Multi-region**: not implemented. This is a single-region stack; a regional AWS outage takes the whole app down.

## Troubleshooting

- **ECS tasks stuck in a pull/start loop right after first apply**: expected — the ECR repos are empty until you push an image (see "ECR image workflow"). Check `aws ecs describe-services` / the ECS console's "Tasks" tab for the actual stopped-reason.
- **Backend task starts then immediately dies**: almost always a missing/wrong secret. Check the task's CloudWatch log group (`/ecs/<prefix>/backend`) — a `DATABASE_URL` or `REDIS_URL` connection failure shows up immediately in the first few log lines.
- **`terraform apply` fails on a Secrets Manager resource with "already scheduled for deletion"**: you destroyed and immediately re-applied. Secrets Manager soft-deletes for a recovery window (0 days in dev via `recovery_window_in_days`, so this shouldn't happen in dev — it can happen in staging/prod where that's 30 days; either wait or force-delete via the CLI with `--force-delete-without-recovery` if you're certain).
- **`terraform plan` shows the ECS task definition changing on every plan**: shouldn't happen — both services have `lifecycle.ignore_changes = [task_definition]` specifically so CI-driven deploys don't fight Terraform. If you see this, check whether something outside Terraform (e.g. a manual `update-service`) changed the *service's* desired task definition in a way Terraform now disagrees with structurally, not just by revision number.
- **Telemetry consumer / simulator services don't exist after apply**: expected when `enable_kafka = false` (the dev default) — see "Kafka / event streaming" below.

## Cleanup instructions

```bash
# Tear down everything Terraform manages:
terraform destroy -var-file=environments/dev.tfvars

# Images pushed to ECR are NOT removed by terraform destroy if the
# repository has images in it and force_destroy-equivalent isn't set on
# the ECR resource (it isn't, deliberately, to avoid silently losing image
# history) — destroy will fail with "repository not empty" until you
# either delete the images manually or add force_delete = true to
# aws_ecr_repository in ecr.tf.
aws ecr batch-delete-image --repository-name robot-fleet-dev-backend --image-ids "$(aws ecr list-images --repository-name robot-fleet-dev-backend --query 'imageIds' --output json)"
aws ecr batch-delete-image --repository-name robot-fleet-dev-frontend --image-ids "$(aws ecr list-images --repository-name robot-fleet-dev-frontend --query 'imageIds' --output json)"
```

Also worth checking manually after a destroy: CloudWatch log groups
sometimes outlive a hurried destroy if a dependency ordering issue
interrupts it partway — `aws logs describe-log-groups --log-group-name-prefix /ecs/robot-fleet-dev` to confirm none are left behind and quietly accruing storage cost.

## Known limitations

- No staging/prod tfvars exist yet — only `dev` (see "Adding staging/prod later").
- No remote state configured by default (local state only) — see "Remote state".
- No WAF, no CloudFront/CDN, no multi-region.
- Frontend has no test script in `package.json` — CI only lints and builds it.
- The image-push-to-ECR and ECS-deploy steps of the CI/CD pipeline are **documented but not implemented** (see below) — they need an AWS OIDC role ARN configured as a repo secret first, which is a deliberate, explicit setup step, not something this PR does on your behalf.
- MSK, when enabled, uses network isolation as its only access control (no SASL/SCRAM/IAM client auth).
- No autoscaling configured on any ECS service — `desired_count` is fixed.
- The backend's own code doesn't call S3 yet (the IAM grant is provisioned for the documented future use case, not proof the feature exists).

## Future production hardening tasks

1. Separate AWS accounts per environment (dev/staging/prod), not just separate resource names in one account.
2. Remote state + DynamoDB locking (see "Remote state") before more than one person touches this.
3. `db_multi_az = true`, `db_deletion_protection = true`, `db_skip_final_snapshot = false`, `redis_replica_count >= 1` for anything beyond dev.
4. WAF in front of the ALB; consider CloudFront for edge caching/DDoS absorption.
5. ECS service autoscaling (target tracking on CPU/memory or request count per target).
6. MSK client authentication (SASL/SCRAM or IAM) if Kafka is enabled for staging/prod.
7. Secret rotation (Secrets Manager supports automatic RDS credential rotation natively).
8. Tighten the GitHub OIDC trust policy's `sub` condition from "any ref in this repo" to a specific branch (e.g. `refs/heads/main`) once you want deploys gated to a protected branch.
9. A real CI/CD deploy workflow (see below) with a required manual approval gate for anything touching prod.
10. Application-level observability — this stack gives you infrastructure metrics/logs only; add OpenTelemetry/structured logging in the FastAPI app itself for request tracing, which infrastructure monitoring cannot substitute for.

## CI/CD preparation

Three workflows exist today, all safe-by-default (no AWS credentials, no
deploy, nothing destructive):

- `.github/workflows/terraform-validate.yml` — `fmt -check` + `validate` on any PR touching `infrastructure/terraform/`.
- `.github/workflows/backend-tests.yml` — runs `pytest` against the real `docker-compose.yml` services.
- `.github/workflows/frontend-build.yml` — `npm ci && npm run lint && npm run build`.

The full pipeline this stack is designed for, in order — steps 1-6 exist
today, 7-10 are documented here deliberately rather than implemented, since
they need an AWS OIDC role ARN configured as a repository secret/variable
first (a one-time, explicit, human-run setup step — see
`github_actions_deploy_role_arn` in `terraform output`):

1. Run backend tests — **implemented**
2. Run frontend build — **implemented**
3. Build Docker images — documented above ("ECR image workflow"), not yet wired into CI
4. Push images to ECR (using the OIDC role's push-only permissions in `iam.tf`)
5. Authenticate to AWS using GitHub OIDC (`aws-actions/configure-aws-credentials` with `role-to-assume: <github_actions_deploy_role_arn>`)
6. Run `terraform fmt`/`validate` — **implemented**
7. Run `terraform plan` (needs AWS credentials — a second, broader-permissioned role than the deploy role above; not created by this stack, since plan/apply access is a materially bigger grant than "push an image and update a known service")
8. Require manual approval before anything resembling a prod apply (GitHub Environments with required reviewers is the standard mechanism)
9. Deploy: `aws ecs register-task-definition` with the new image tag, then `aws ecs update-service --force-new-deployment`
10. Smoke test: `curl -sf $(terraform output -raw app_url)/health` and a couple of authenticated endpoint checks

Steps 7-9 deliberately are not implemented as GitHub Actions in this
change — per the instructions this stack was built under, automatic
deployment (especially anything that could reach prod) needs its own
explicit setup and sign-off, not a default that ships enabled.
