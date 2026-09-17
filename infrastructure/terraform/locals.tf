locals {
  # Deterministic prefix for every resource name: e.g. "robot-fleet-dev".
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  # /24s carved out of the /16 VPC CIDR: 10.0.0.0/24, 10.0.1.0/24, ... one
  # block per subnet tier per AZ. Comfortably supports az_count up to 4
  # per tier (12 subnets total) without overlap, with room to grow.
  public_subnet_cidrs = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i)]
  app_subnet_cidrs    = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 10)]
  data_subnet_cidrs   = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 20)]

  is_prod = var.environment == "prod"

  # Path prefixes routed to the backend ECS service via ALB listener rules;
  # everything else falls through to the default rule (frontend service).
  # Kept in one place since both the ALB listener rules and the README's
  # architecture description need to stay in sync with the app's actual
  # route prefixes (backend/app/main.py's include_router calls).
  backend_path_patterns = ["/robots*", "/auth*", "/agent*", "/ws*", "/documents*", "/incidents*", "/health"]
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}
