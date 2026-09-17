variable "project_name" {
  description = "Short name used as a prefix for all resource names and tags."
  type        = string
  default     = "robot-fleet"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.project_name))
    error_message = "project_name must be lowercase alphanumeric/hyphens, start with a letter, and be 2-21 characters."
  }
}

variable "environment" {
  description = "Deployment environment. Controls dev-vs-prod-safe defaults used throughout the config (see locals.tf)."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "aws_region" {
  description = "AWS region to deploy into. us-east-1 chosen as a low-cost default with full service availability (MSK, ElastiCache, etc.) for this stack; change freely."
  type        = string
  default     = "us-east-1"
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the CI/CD deploy role via OIDC, as \"owner/repo\" (e.g. \"elgin-vuong/Robot-Fleet-Management-System\"). Required for the GitHub Actions OIDC trust policy in iam.tf to be scoped correctly; leave the default only if you don't intend to wire up CI/CD deployment yet."
  type        = string
  default     = "OWNER/REPO"
}

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid IPv4 CIDR block."
  }
}

variable "az_count" {
  description = "Number of Availability Zones to spread subnets across. 2 is the minimum for anything with an ALB/RDS Multi-AZ; kept configurable for staging/prod to use 3."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 4
    error_message = "az_count must be between 2 and 4."
  }
}

variable "nat_strategy" {
  description = <<-EOT
    How many NAT Gateways to create, trading cost against availability:
      - "single"     : one NAT Gateway shared by all private subnets (cheapest; a single AZ failure
                        can interrupt outbound internet access for private-subnet workloads). Recommended for dev.
      - "one_per_az"  : one NAT Gateway per AZ (highest availability, cost scales with az_count). Recommended for prod.
      - "none"        : no NAT Gateway at all. Only viable if nothing in the private app subnets needs
                        outbound internet access (this app's backend calls the Anthropic/Voyage AI APIs and
                        pulls container images, so "none" will break it unless VPC endpoints cover every
                        external call it makes — not recommended).
  EOT
  type        = string
  default     = "single"

  validation {
    condition     = contains(["single", "one_per_az", "none"], var.nat_strategy)
    error_message = "nat_strategy must be one of: single, one_per_az, none."
  }
}

variable "domain_name" {
  description = "Optional Route 53 hosted zone / domain name for the app (e.g. \"fleet.example.com\"). Leave empty to skip Route 53 + ACM and expose the ALB directly over HTTP via its AWS-generated DNS name."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Kafka / event streaming
# ---------------------------------------------------------------------------

variable "enable_kafka" {
  description = <<-EOT
    Whether to create a managed Kafka cluster (Amazon MSK). Default false:
    a minimally-sized MSK cluster costs real money 24/7 whether or not it's used
    (~$60+/month for 2x kafka.t3.small brokers, before storage/data transfer).
    Local development keeps using the existing docker-compose.yml Kafka container
    regardless of this flag. Flip to true only when you actually need a shared,
    durable Kafka cluster (e.g. staging/prod, or a dev cluster you'll destroy after use).
  EOT
  type        = bool
  default     = false
}

variable "kafka_broker_instance_type" {
  description = "MSK broker instance type. Only used when enable_kafka = true."
  type        = string
  default     = "kafka.t3.small"
}

variable "kafka_broker_count" {
  description = "Number of MSK brokers (one per AZ minimum for durability). Only used when enable_kafka = true."
  type        = number
  default     = 2

  validation {
    condition     = var.kafka_broker_count >= 2
    error_message = "kafka_broker_count must be at least 2 for broker-loss durability."
  }
}

variable "kafka_ebs_volume_size" {
  description = "Per-broker EBS storage in GiB. Only used when enable_kafka = true."
  type        = number
  default     = 100
}

# ---------------------------------------------------------------------------
# Database (RDS PostgreSQL)
# ---------------------------------------------------------------------------

variable "db_engine_version" {
  description = "PostgreSQL engine version. Must be >= 15.2 / 16.1 for CREATE EXTENSION vector (pgvector) support, which this app requires for document search."
  type        = string
  default     = "16.4"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Initial RDS storage in GiB."
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Ceiling for RDS storage autoscaling in GiB (set equal to db_allocated_storage to disable autoscaling)."
  type        = number
  default     = 100
}

variable "db_name" {
  description = "Application database name."
  type        = string
  default     = "robot_fleet"
}

variable "db_username" {
  description = "Master username for RDS. The password is generated by Terraform (random_password) and stored only in Secrets Manager — never set it here."
  type        = string
  default     = "fleet_admin"
}

variable "db_multi_az" {
  description = "Whether RDS runs a synchronous standby in a second AZ. Roughly doubles RDS cost; recommended true for staging/prod, false for dev."
  type        = bool
  default     = false
}

variable "db_deletion_protection" {
  description = "Whether to block accidental RDS deletion via the API/console/Terraform. Should be true for staging/prod."
  type        = bool
  default     = false
}

variable "db_skip_final_snapshot" {
  description = "Whether to skip taking a final snapshot when the RDS instance is destroyed. false (i.e. take a snapshot) is recommended for staging/prod; true is convenient for a disposable dev environment."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "Automated RDS backup retention period in days (0 disables automated backups)."
  type        = number
  default     = 3
}

# ---------------------------------------------------------------------------
# Cache (ElastiCache Redis)
# ---------------------------------------------------------------------------

variable "redis_node_type" {
  description = "ElastiCache node instance type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "redis_engine_version" {
  description = "ElastiCache Redis engine version."
  type        = string
  default     = "7.1"
}

variable "redis_replica_count" {
  description = "Number of replica nodes (0 = single node, no failover — fine for dev; use >= 1 with automatic failover for staging/prod)."
  type        = number
  default     = 0

  validation {
    condition     = var.redis_replica_count >= 0 && var.redis_replica_count <= 5
    error_message = "redis_replica_count must be between 0 and 5."
  }
}

variable "redis_transit_encryption_enabled" {
  description = "Whether to require TLS between the app and Redis. Requires the app to connect using a rediss:// URL and an AUTH token (both handled by this stack); recommended true even in dev since it costs nothing extra."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------------
# Compute (ECS Fargate)
# ---------------------------------------------------------------------------

variable "backend_image_tag" {
  description = "Tag of the backend image in ECR to deploy (see README 'ECR image workflow'). No default on purpose in staging/prod usage — pin to an immutable tag (e.g. a git SHA), not \"latest\"."
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  description = "Tag of the frontend image in ECR to deploy."
  type        = string
  default     = "latest"
}

variable "backend_cpu" {
  description = "Fargate vCPU units for the backend API task (1024 = 1 vCPU)."
  type        = number
  default     = 256
}

variable "backend_memory" {
  description = "Fargate memory (MiB) for the backend API task."
  type        = number
  default     = 512
}

variable "backend_desired_count" {
  description = "Desired number of running backend API tasks."
  type        = number
  default     = 1
}

variable "frontend_cpu" {
  description = "Fargate vCPU units for the frontend task."
  type        = number
  default     = 256
}

variable "frontend_memory" {
  description = "Fargate memory (MiB) for the frontend task."
  type        = number
  default     = 512
}

variable "frontend_desired_count" {
  description = "Desired number of running frontend tasks."
  type        = number
  default     = 1
}

variable "worker_cpu" {
  description = "Fargate vCPU units for each background worker task (telemetry consumer, simulator)."
  type        = number
  default     = 256
}

variable "worker_memory" {
  description = "Fargate memory (MiB) for each background worker task."
  type        = number
  default     = 512
}

variable "enable_simulator_worker" {
  description = "Whether to run the robot simulator as an ECS service. It only generates demo telemetry — safe to leave off (false) to save a small amount of Fargate cost, and easy to scale to 0 desired count instead of destroying it."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

variable "log_retention_days" {
  description = "CloudWatch Logs retention in days for all application log groups."
  type        = number
  default     = 14
}

variable "alarm_email" {
  description = "Optional email address to subscribe to the CloudWatch alarm SNS topic. Leave empty to create the topic without a subscription (alarms still fire and are visible in the console, just not emailed)."
  type        = string
  default     = ""
  sensitive   = true
}

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

variable "s3_bucket_name_override" {
  description = "Optional explicit S3 bucket name. S3 bucket names are globally unique across all AWS accounts, so by default this stack derives a name from project/environment/account/region via random_id; set this only if you need a specific name."
  type        = string
  default     = ""
}
