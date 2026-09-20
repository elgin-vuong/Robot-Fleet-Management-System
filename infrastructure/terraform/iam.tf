# IAM is implemented directly at root (not as a module) because every role
# here references ARNs from several other modules (Secrets Manager, S3,
# ECR, ECS) — a dedicated module would just import all of that back in
# through its variables with no real encapsulation benefit.
#
# Three distinct roles, deliberately not merged into one "do everything"
# role:
#   1. ECS task EXECUTION role  — what Fargate itself uses to pull images
#      and resolve `secrets` block values before your code ever runs.
#   2. ECS task ROLE(s)         — what your application code can do at
#      runtime via the AWS SDK (S3 access for exports, etc).
#   3. GitHub Actions DEPLOY role — what CI/CD can do (push images, update
#      services). Deliberately excludes Terraform apply permissions — see
#      README "CI/CD preparation" for why that's a separate, more sensitive
#      role this stack does not create.

########################################
# 1. ECS task execution role
########################################

data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${local.name_prefix}-ecs-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# The managed policy above covers ECR pull + CloudWatch Logs. It does NOT
# cover reading Secrets Manager values for the `secrets` block on each
# container definition — that needs an explicit, scoped grant.
data "aws_iam_policy_document" "ecs_task_execution_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.db_credentials.arn,
      aws_secretsmanager_secret.jwt_secret.arn,
      aws_secretsmanager_secret.ai_api_key.arn,
      aws_secretsmanager_secret.voyage_api_key.arn,
    ]
  }

  dynamic "statement" {
    for_each = var.redis_transit_encryption_enabled ? [1] : []
    content {
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [aws_secretsmanager_secret.redis_auth[0].arn]
    }
  }
}

resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name   = "${local.name_prefix}-secrets-read"
  role   = aws_iam_role.ecs_task_execution.id
  policy = data.aws_iam_policy_document.ecs_task_execution_secrets.json
}

########################################
# 2. ECS task roles (runtime AWS access for application code)
########################################

data "aws_iam_policy_document" "s3_app_bucket_access" {
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [module.storage.bucket_arn]
  }

  statement {
    sid       = "ReadWriteObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${module.storage.bucket_arn}/*"]
  }
}

# Backend API task role. Note: as of this Terraform, the backend's own
# Python code does not yet call S3 directly (no boto3 usage in
# backend/app/) — this grant exists so the documented "S3 for
# exports/telemetry artifacts" use case (task H) can be implemented in the
# app later without an IAM change. Narrow further if that never happens.
resource "aws_iam_role" "backend_task" {
  name               = "${local.name_prefix}-backend-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "backend_task_s3" {
  name   = "${local.name_prefix}-backend-s3"
  role   = aws_iam_role.backend_task.id
  policy = data.aws_iam_policy_document.s3_app_bucket_access.json
}

resource "aws_iam_role" "worker_task" {
  name               = "${local.name_prefix}-worker-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "worker_task_s3" {
  name   = "${local.name_prefix}-worker-s3"
  role   = aws_iam_role.worker_task.id
  policy = data.aws_iam_policy_document.s3_app_bucket_access.json
}

########################################
# 3. GitHub Actions OIDC deploy role — no long-lived AWS access keys.
# Scoped to: push images to THIS project's ECR repos, update THIS
# project's ECS services. Cannot touch IAM, Terraform state, or any
# resource outside those two things.
########################################

resource "aws_iam_openid_connect_provider" "github_actions" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS validates the GitHub OIDC endpoint against its own trusted CA store
  # regardless of this value (has been true since ~2023); it's required by
  # the resource schema but no longer security-critical. This is GitHub's
  # long-documented root CA thumbprint.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = local.common_tags
}

data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Restricted to THIS repo's main branch only — .github/workflows/docker.yml
    # is the only workflow that ever requests id-token: write and calls
    # aws-actions/configure-aws-credentials, and only on push-to-main (never
    # on pull_request, including PRs from this same repo). This condition is
    # the backstop for that: even if a future workflow change added OIDC to a
    # PR-triggered job, AWS itself would still refuse to hand out credentials
    # for anything but a real push to refs/heads/main.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions_deploy" {
  name               = "${local.name_prefix}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "github_actions_deploy" {
  statement {
    sid       = "ECRAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # GetAuthorizationToken does not support resource-level scoping
  }

  statement {
    sid = "ECRPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
    ]
    resources = [aws_ecr_repository.backend.arn, aws_ecr_repository.frontend.arn]
  }

  statement {
    sid = "ECSDeploy"
    actions = [
      "ecs:DescribeServices",
      "ecs:DescribeTaskDefinition",
      "ecs:RegisterTaskDefinition",
      "ecs:UpdateService",
    ]
    resources = ["*"] # RegisterTaskDefinition does not support resource-level scoping; UpdateService/DescribeServices scoped below is not possible without wildcards in this API family
  }

  statement {
    sid     = "PassTaskRoles"
    actions = ["iam:PassRole"]
    resources = [
      aws_iam_role.ecs_task_execution.arn,
      aws_iam_role.backend_task.arn,
      aws_iam_role.worker_task.arn,
    ]
  }
}

resource "aws_iam_role_policy" "github_actions_deploy" {
  name   = "${local.name_prefix}-github-deploy"
  role   = aws_iam_role.github_actions_deploy.id
  policy = data.aws_iam_policy_document.github_actions_deploy.json
}
