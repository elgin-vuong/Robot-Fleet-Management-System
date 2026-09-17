# One backend image serves the API, telemetry-consumer, and simulator
# ECS task definitions (same image, different container `command` — see
# compute module) — so only two repositories are needed, not one per
# service. See README "ECR image workflow" for build/push/deploy commands.

resource "aws_ecr_repository" "backend" {
  name                 = "${local.name_prefix}-backend"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}

resource "aws_ecr_repository" "frontend" {
  name                 = "${local.name_prefix}-frontend"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}

# Keep the last 10 tagged images and expire anything untagged after a day —
# untagged images accumulate from repeated pushes during development and
# otherwise sit there forever, at (small but nonzero) storage cost.
locals {
  ecr_lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the last 10 tagged images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name
  policy     = local.ecr_lifecycle_policy
}

resource "aws_ecr_lifecycle_policy" "frontend" {
  repository = aws_ecr_repository.frontend.name
  policy     = local.ecr_lifecycle_policy
}
