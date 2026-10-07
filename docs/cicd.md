# CI/CD

How code gets from a feature branch to a running AWS service, what runs
where, what's required to set it up, and how to debug it when it breaks.

## 1. CI architecture

```mermaid
flowchart LR
    DEV[Developer] --> PR[Pull Request]

    PR --> BCI["Backend CI\n(format, lint, pytest)"]
    PR --> FCI["Frontend CI\n(lint, typecheck, build)"]
    PR --> TF["Terraform\n(fmt, validate)"]
    PR --> DOCKER["Docker\n(build + Trivy scan, not pushed)"]

    BCI --> GATE["CI passed\n(required check)"]
    FCI --> GATE
    TF --> GATE
    DOCKER --> GATE

    GATE --> REVIEW[Code review]
    REVIEW --> MERGE[Merge to main]

    MERGE --> MAINCI["Same tests + build + push\n(git-SHA tag)"]
    MAINCI --> MAINGATE["CI passed"]
    MAINGATE --> OIDC[GitHub OIDC]
    OIDC --> IAMROLE[AWS IAM Role - github_actions_deploy]
    IAMROLE --> ECR[Amazon ECR]

    ECR --> DEPLOY["Deploy to ECS - dev\n(backend + frontend services)"]
    DEPLOY --> HEALTH["Smoke test - GET /health/ready"]
    HEALTH --> SUCCESS[Deployment complete]

    HEALTH -.rollback via circuit breaker.-> DEPLOY
```

One pipeline, `.github/workflows/ci-cd.yml`, triggered on every PR and
every push to `main`. It calls three reusable workflows for the checks and
owns the build and deploy jobs itself:

| File | Called when (path filter) | Purpose |
|---|---|---|
| `.github/workflows/ci-cd.yml` | always runs | Detects what changed, calls the checks below, builds images, gates on `CI passed`, deploys on `main`. The only workflow that ever touches AWS |
| `.github/workflows/backend-ci.yml` | `backend/**`, `docker-compose.yml`, `pyproject.toml` | Format check, lint, real pytest suite against real Postgres/Redis/Kafka |
| `.github/workflows/frontend-ci.yml` | `frontend/**` | Lint, type-check, production build |
| `.github/workflows/terraform.yml` | `infrastructure/terraform/**` | `fmt -check`, `validate` — no AWS credentials |

Each reusable workflow's own file also counts as a change to it, and
editing `ci-cd.yml` counts as a change to everything, so a pipeline change
is always exercised end to end before it merges.

**Why one pipeline:** `deploy-dev` `needs:` the test jobs, so a push to
`main` can never deploy a commit whose own tests failed. When CI and the
deploy were separate workflows, they ran side by side and the deploy went
ahead regardless of the test result on that same push. (`workflow_run`
can't fix that cleanly: it can't wait on more than one upstream workflow,
and doesn't fire at all when the upstream was path-filtered out.)

**Pull request validation** = whichever checks the path filter selects,
plus the image build-and-scan jobs, all rolled up into the single
`CI passed` job. Nothing in a PR run — including PRs from this same
repository — ever requests AWS credentials. **Main branch validation** is
the same, but the build jobs additionally push images, and `deploy-dev`
runs once `CI passed` succeeds.

## 2-6. Workflow files

### Backend CI (`backend-ci.yml`)

Two jobs:
- **Backend Formatting & Lint** — `ruff format --check` then `ruff check`, both from `backend/requirements-dev.txt` (ruff is dev/CI-only, deliberately not in the production image — see `backend/requirements-dev.txt`'s own comment).
- **Backend Tests** — starts `postgres`, `redis`, `kafka` from the repo's own root `docker-compose.yml` (not GitHub Actions service containers — this repo's Kafka needs a specific dual-listener KRaft setup for a host process to reach it, which already exists there and is exercised daily in local dev; duplicating an equivalent as inline `services:` would just be a second, drifting copy of the same config), waits for both to be ready, runs `alembic upgrade head`, then `pytest`.

Ruff's rule selection is deliberately the classic minimal set
(`E4,E7,E9,F` — pyflakes plus basic pycodestyle), not ruff's own broader
default preset, and `E402` is explicitly ignored because
`backend/app/main.py` and `backend/app/consumers/telemetry_consumer.py`
intentionally import *after* calling
`configure_logging()`/`configure_tracing()`/`load_dotenv()`, so those take
effect before any other `backend.app` import runs. See `pyproject.toml`'s
`[tool.ruff]` section.

### Frontend CI (`frontend-ci.yml`)

One job: `npm ci` (lockfile-pinned, reproducible — not `npm install`),
`npm run lint` (oxlint), `npm run typecheck` (`tsc -b --noEmit` — added as
its own script; previously type-checking only happened implicitly inside
`npm run build`), `npm run build`. **No test framework exists in this
repo's frontend yet** — see "Known limitations."

### Terraform (`terraform.yml`)

`terraform fmt -check -recursive`, `terraform init -backend=false`,
`terraform validate`. No AWS credentials, ever, for this workflow — see
"Known limitations" for why `terraform plan` isn't wired into CI.

### CI/CD pipeline (`ci-cd.yml`)

The one workflow with real AWS access. Its own jobs, besides calling the
three workflows above:

1. **`changes`** (`Detect changes`) — `dorny/paths-filter` works out which of backend / frontend / terraform / images changed; every other job keys off its outputs. There's deliberately no workflow-level `paths:` filter: a workflow that never starts leaves a required status check pending forever, so the workflow always runs and skips individual jobs instead.
2. **`build-backend`** / **`build-frontend`** — run when `backend/**`, `frontend/**` or `.dockerignore` changed (both images are always built together, because `deploy-dev` deploys both at the same SHA). On a PR: `docker buildx build` (no push), then a Trivy scan for `CRITICAL` vulnerabilities (fails the job if any are found). On push to `main`: same build, plus push to ECR tagged `:<git-sha>`, plus the same Trivy scan against the real pushed image.
3. **`ci-passed`** (`CI passed`) — `needs:` every check and build job and runs `if: always()`. Fails if any of them failed or was cancelled; passes if they succeeded or were skipped by the path filter. This is the **one** status check branch protection should require (see #15).
4. **`deploy-dev`** — only on push to `main`, `needs: [ci-passed, build-backend, build-frontend]`, and only if all three succeeded. (It uses `!cancelled()` instead of the default `success()` so that a test job legitimately skipped by the path filter doesn't skip the deploy too.) Fetches each service's current ECS task definition, renders in the new image (`aws-actions/amazon-ecs-render-task-definition`), deploys it (`aws-actions/amazon-ecs-deploy-task-definition`, `wait-for-service-stability: true`), then smoke-tests `GET /health/ready`.

Concurrency: on a PR, a new push cancels the previous, now-stale run. On
`main`, runs queue rather than cancel, so a deploy is never interrupted
halfway through. If several merges land at once, GitHub keeps only the
newest pending run, which is fine because it deploys the newest SHA.

## 7. ECR authentication / 8. GitHub OIDC

```
GitHub Actions (ci-cd.yml, push-to-main only)
      │  requests an OIDC token, aud=sts.amazonaws.com
      ▼
AWS IAM OIDC provider (infrastructure/terraform/iam.tf: github_actions)
      │  trust policy checks token's "sub" claim equals
      │  repo:<github_repository>:ref:refs/heads/main  — exact match, not a
      │  wildcard (tightened as part of this change; previously matched any
      │  ref in the repo, which would have let a PR-triggered workflow
      │  assume the same role if one were ever added carelessly)
      ▼
aws_iam_role.github_actions_deploy
      │  scoped to: ecr:GetAuthorizationToken + push actions on this
      │  repo's two ECR repos; ecs:DescribeServices/DescribeTaskDefinition/
      │  RegisterTaskDefinition/UpdateService; iam:PassRole for the three
      │  ECS task roles. Nothing else — no EC2/RDS/IAM/VPC read access, so
      │  it cannot run `terraform plan`.
      ▼
Amazon ECR (push) + Amazon ECS (deploy)
```

This role and its OIDC provider **already existed** from the AWS
infrastructure work (`infrastructure/terraform/iam.tf`) before this CI/CD
change — reused here, not duplicated. **No AWS access keys exist anywhere
in this repository, in GitHub secrets, or in any workflow file.**

## 9. Image tagging

Every image pushed to ECR gets exactly one tag: the git SHA
(`robot-fleet-dev-backend:<40-char-sha>`), and the deploy job deploys by
that SHA. There is deliberately no floating `:main`/`:latest` tag — the
repositories are `IMMUTABLE` (below), so a floating tag could only ever be
pushed once and every later push to `main` would fail at the build step.
(An earlier version of the pipeline did push `:main` and would have hit
exactly that on its second deploy.) To find the newest image, sort by push
date: `aws ecr describe-images --repository-name robot-fleet-dev-backend
--query 'sort_by(imageDetails,&imagePushedAt)[-1].imageTags'`.

Because the tag *is* the commit, you can always answer
"exactly which commit produced the image currently running in dev" by
reading the ECS task definition's image URI.

PR builds get a `pr-<number>` tag but are **never pushed anywhere** — they
exist only inside that CI run, to prove the build succeeds and pass the
Trivy scan.

Both ECR repositories (`infrastructure/terraform/ecr.tf`) are
`IMMUTABLE` — once a tag is pushed, AWS itself refuses to let it be
overwritten.

## 10. Deployment flow

```
push to main
   │
   ├─ changes ─┬─ backend-ci   ─┐   (each only if its paths changed;
   │           ├─ frontend-ci  ─┤    skipped counts as passing)
   │           ├─ terraform    ─┤
   │           ├─ build-backend ┤
   │           └─ build-frontend┤
   │                            ▼
   │                        ci-passed
   │                            │
   │                            ▼
   │              deploy-dev
   │                    │
   │                    ├─ render + deploy backend task definition
   │                    ├─ wait for backend service stability
   │                    ├─ render + deploy frontend task definition
   │                    ├─ wait for frontend service stability
   │                    └─ curl {APP_HEALTH_URL}/health/ready, retrying
   │                       10x/10s
   │
   └─ (any test or build failing fails ci-passed — nothing deploys)
```

Both ECS services have `deployment_circuit_breaker { enable = true,
rollback = true }` (added to `infrastructure/terraform/modules/compute/
services.tf` as part of this change — it didn't exist before and without
it, a task definition that never passes its health check would just sit
there forever instead of failing). That means: if the new task definition
never reports healthy, ECS gives up after enough failed attempts,
automatically reverts the service to the last known-good task definition
on its own, and the GitHub Actions `wait-for-service-stability` step fails
promptly instead of hanging until the job times out.

## 11. GitHub environments / 12. Production approval

**No GitHub Environment is used**, deliberately: `deploy-dev` has no
`environment:` key. Declaring one changes the OIDC token's `sub` claim
from `repo:<repo>:ref:refs/heads/main` to `repo:<repo>:environment:<name>`,
and the IAM trust policy (`infrastructure/terraform/iam.tf`, see #7/#8)
only accepts the former — so with `environment: dev` the deploy job's
AssumeRole was refused even though the build jobs (no environment) could
log in fine. An earlier version of this pipeline had exactly that bug.

To use a GitHub Environment later (deployment history in the UI, required
reviewers, environment-scoped variables), all three are needed together:
add `"repo:${var.github_repository}:environment:dev"` to the `sub`
condition's `values` in `iam.tf` and `terraform apply`; restrict the `dev`
Environment's **Deployment branches** to `main` only in GitHub (otherwise
any branch's workflow could declare `environment: dev` and get AWS
credentials, bypassing the main-only restriction); then add
`environment: dev` back to `deploy-dev`.

Only one AWS environment actually exists
(`infrastructure/terraform/environments/dev.tfvars`). There is
**no `staging` or `production` environment, no manual-approval-gated job,
and no automatic production deployment** — because there's no staging/prod
AWS infrastructure for it to deploy to yet. Building an approval-gated
`production` job now that silently deployed to the same dev cluster would
be misleading; building one that always fails would just be dead code. See
"Known limitations" for the concrete extension path once real staging/prod
Terraform environments exist.

**Configure now** (needs a GitHub UI action — not something this PR can do
on your behalf): add these three as **repository variables** (Settings →
Secrets and variables → Actions → Variables tab), sourced from
`terraform output` after `apply`:

| Variable | Source |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `terraform output -raw github_actions_deploy_role_arn` |
| `AWS_REGION` | whatever `aws_region` you applied with (default `us-east-1`) |
| `APP_HEALTH_URL` | `terraform output -raw app_url` |

They must be repository-level, not on an Environment: environment-scoped
variables only resolve in jobs that declare that `environment:`, and none
of these jobs do.

## 13. Rollback procedure

Because every deploy is by immutable SHA, rolling back is "deploy the
previous SHA," not a special operation:

1. Find the last known-good SHA — either the previous successful run of
   `ci-cd.yml` in the Actions tab, or `git log --oneline main`.
2. Re-run the **`deploy-dev`** job manually (Actions → the workflow run for
   that commit → "Re-run jobs" → "Re-run failed jobs" or the whole run),
   which re-renders and re-deploys that exact image SHA — nothing needs to
   be rebuilt, since the image is already in ECR immutably.
3. Alternatively, from a local machine with AWS credentials:
   ```bash
   aws ecs describe-task-definition --task-definition robot-fleet-dev-backend --query taskDefinition > td.json
   # edit td.json's image field to the previous SHA, or use the render action's
   # logic by hand, then:
   aws ecs register-task-definition --cli-input-json file://td.json
   aws ecs update-service --cluster robot-fleet-dev-cluster --service robot-fleet-dev-backend --task-definition <new-revision-arn>
   ```
4. Watch `aws ecs wait services-stable` (or the ECS console) and re-check `GET /health/ready`.
5. Keep monitoring — the circuit breaker means a *second* bad deploy on top of a rollback would also auto-revert, but it won't retroactively fix anything already wrong before you rolled back.

No automatic rollback-on-alert is implemented — only the deploy-time
circuit breaker described above. A "revert automatically if error rates
spike an hour later" mechanism would need real application-level alerting
wired to a rollback trigger, which is out of scope here and genuinely
risky to build without careful thought (see "Known limitations").

## 14. Troubleshooting

- **`Backend CI / Backend Tests`'s "Wait for Kafka" step times out**: check the `docker compose logs` step's output (runs automatically `if: failure()`) — usually a KRaft controller-quorum config issue, not a test problem.
- **`ruff format --check` fails on a PR**: run `ruff format backend/` locally (`pip install -r backend/requirements-dev.txt` first) and commit the result — don't hand-fix formatting to match ruff's opinion.
- **`ci-cd.yml`'s AWS steps fail with "Not authorized to perform sts:AssumeRoleWithWebIdentity"**: almost always one of — (a) `AWS_DEPLOY_ROLE_ARN` isn't set as a repository variable (an Environment-scoped one won't be seen — see #11), (b) the workflow run isn't a push to `main` (the trust policy only allows that exact ref), (c) Terraform hasn't actually been applied yet so the role doesn't exist, or (d) someone added `environment:` to the job, which changes the token's `sub` claim (see #11).
- **`deploy-dev` hangs on "wait for service stability"**: shouldn't happen now that the circuit breaker is enabled (see #10) — if it does, check the ECS service's "Deployments" tab in the console for the actual stopped-reason on failing tasks (almost always a missing/wrong Secrets Manager value — see the Terraform README's own "Troubleshooting").
- **`CI passed` fails but every other job is green**: one of them was cancelled (e.g. by a newer push to the same PR) — look for a grey "cancelled" job and re-run.
- **`Deploy (dev)` shows as skipped on a push to `main`**: expected when no image changed (e.g. a docs- or Terraform-only commit) — both build jobs were skipped, so there's nothing new to deploy. If images did change, check `CI passed`: a failing test blocks the deploy by design.
- **Smoke test fails but the ECS deployment itself succeeded**: `APP_HEALTH_URL` is probably wrong/stale, or the ALB's DNS hasn't propagated yet in a very fresh environment — re-run just that step.

## 15. Required GitHub repository configuration (branch protection)

**Not applied automatically** — I don't have GitHub API access or
authorization to change repository settings, and even if I did, changing
branch protection is exactly the kind of action that needs a human
decision, not a default. Configure these by hand under **Settings →
Branches → Branch protection rules** for `main`:

- [x] Require a pull request before merging
- [x] Require status checks to pass before merging — select **only `CI passed`**. It already rolls up every test, lint, Terraform and image-build job. Don't select the individual jobs: each one is skipped whenever its paths didn't change, and listing many of them means editing this setting every time a job is added or renamed. (`CI passed` only appears in the search box after the pipeline has run at least once — open any PR first.)
- [x] Require branches to be up to date before merging
- [x] Require at least 1 approving review
- [x] Require conversation resolution before merging
- [x] Do not allow bypassing the above settings (applies rules to admins too)
- [ ] Do **not** enable "Allow force pushes" or "Allow deletions" on `main`

## 16. Required AWS IAM configuration

Already implemented in `infrastructure/terraform/iam.tf` (this task reused
it, didn't create a new one) — see #7/#8 above for the full trust-policy
and permissions breakdown. Nothing further to configure by hand beyond
running `terraform apply` and copying its outputs into GitHub (below).

## 17. Required repository secrets/variables

No **secrets** are required for CI/CD itself — OIDC replaces long-lived
AWS keys entirely, and the app's own runtime secrets (`AI_API_KEY`,
`JWT_SECRET_KEY`, DB credentials, etc.) live in AWS Secrets Manager, set up
by the Terraform in `infrastructure/terraform/secrets.tf`, never in
GitHub.

**Variables** (repository-level — not environment-scoped; see #11):

| Name | Value |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `terraform output -raw github_actions_deploy_role_arn` |
| `AWS_REGION` | the region you applied with |
| `APP_HEALTH_URL` | `terraform output -raw app_url` |

## 18. Required ECR repositories

Both already defined in `infrastructure/terraform/ecr.tf`:
`robot-fleet-dev-backend` and `robot-fleet-dev-frontend`. `terraform apply`
creates them; `ci-cd.yml` only ever pushes to them, never creates/deletes
a repository itself.

## Known limitations

- **No `terraform plan` in CI.** The existing `github_actions_deploy` IAM role is deliberately scoped to ECR+ECS only and cannot read the rest of the account (VPC, RDS, IAM, ...), so it can't run `plan`. Adding a plan-capable role is a real, separate, more sensitive decision (broad read access across the account, even if write-free) — not something to bundle into a CI/CD change without its own explicit sign-off. If you want this later: a new IAM role with `iam:GetRole`-style read-only + the relevant `Describe*`/`Get*`/`List*` actions for every resource type in the stack (or just `ReadOnlyAccess`, more simply, accepting its breadth), triggered on `pull_request` for the `infrastructure/terraform/**` path, using `hashicorp/setup-terraform`'s `terraform plan` with `-var-file=environments/dev.tfvars` and `-no-color`, posting the plan as a PR comment via `actions/github-script`.
- **No staging/production pipeline stage.** Only `dev` exists as real infrastructure. Extending this once `environments/staging.tfvars`/`prod.tfvars` exist (see the Terraform README's own "Adding staging/prod later"): duplicate `deploy-dev` as `deploy-staging` (auto, same trigger) and `deploy-production` (`environment: production` with required reviewers configured in the GitHub UI, triggered by `workflow_dispatch` with an `image_tag` input rather than automatically on push), each pointed at that environment's own cluster/service names and its own `AWS_DEPLOY_ROLE_ARN`/`APP_HEALTH_URL` variables.
- **telemetry-consumer and simulator aren't deployed by `ci-cd.yml`.** They only exist as ECS services when `enable_kafka = true` (currently `false` in `dev.tfvars`). Once that flips, add two more render/deploy step-pairs to `deploy-dev` for `robot-fleet-dev-telemetry-consumer` and `robot-fleet-dev-simulator`, using the same backend image (just a different task family/service, matching how those two are already defined in `infrastructure/terraform/modules/compute/services.tf`).
- **No frontend test framework.** `frontend-ci.yml` runs everything that exists (lint, typecheck, build) but there's no unit/component test suite to run. Adding one (Vitest is the natural fit alongside Vite) is frontend work, not a CI/CD change, and out of scope here.
- **Frontend Docker image still runs as root.** `nginx:1.27-alpine`'s default user needs root to bind port 80. Switching to `nginx-unprivileged` + port 8080 would fix this but changes the container's exposed port and the ALB target group/health check port it's paired with — a real, coordinated change across the Dockerfile, `docker-compose.yml`, the k8s manifests, and the Terraform compute module, not something to slip into a CI/CD PR unannounced.
- **No automated secret rotation, no cross-environment secret isolation beyond naming** — both already called out in the Terraform README's own "Future production hardening tasks."
