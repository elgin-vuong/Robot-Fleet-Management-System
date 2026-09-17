variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "app_subnet_ids" {
  type = list(string)
}

variable "alb_sg_id" {
  type = string
}

variable "backend_sg_id" {
  type = string
}

variable "frontend_sg_id" {
  type = string
}

variable "worker_sg_id" {
  type = string
}

variable "certificate_arn" {
  description = "ACM certificate ARN. When set, adds an HTTPS listener and redirects HTTP -> HTTPS. Leave null to serve plain HTTP only."
  type        = string
  default     = null
}

variable "enable_container_insights" {
  description = "CloudWatch Container Insights adds per-task/service metrics beyond the basics, at extra CloudWatch cost. Off by default for dev."
  type        = bool
  default     = false
}

variable "log_retention_days" {
  type = number
}

# --- Images ---

variable "backend_image" {
  description = "Full ECR repository URI (no tag) for the backend image, used for the API service and both worker services (same image, different container command)."
  type        = string
}

variable "backend_image_tag" {
  type = string
}

variable "frontend_image" {
  description = "Full ECR repository URI (no tag) for the frontend image."
  type        = string
}

variable "frontend_image_tag" {
  type = string
}

variable "backend_container_port" {
  type    = number
  default = 8000
}

variable "frontend_container_port" {
  type    = number
  default = 80
}

variable "backend_path_patterns" {
  type = list(string)
}

# --- Sizing ---

variable "backend_cpu" {
  type = number
}

variable "backend_memory" {
  type = number
}

variable "backend_desired_count" {
  type = number
}

variable "frontend_cpu" {
  type = number
}

variable "frontend_memory" {
  type = number
}

variable "frontend_desired_count" {
  type = number
}

variable "worker_cpu" {
  type = number
}

variable "worker_memory" {
  type = number
}

variable "enable_telemetry_consumer" {
  description = "Whether to run the telemetry-consumer worker. It needs a reachable Kafka broker to do anything useful — the root module passes var.enable_kafka here, since deploying it without Kafka would just crash-loop."
  type        = bool
}

variable "enable_simulator_worker" {
  description = "Whether to run the simulator worker. Like the telemetry consumer, it needs Kafka; the root module passes var.enable_kafka && var.enable_simulator_worker here."
  type        = bool
}

# --- IAM (created at root — see root iam.tf) ---

variable "task_execution_role_arn" {
  type = string
}

variable "backend_task_role_arn" {
  type = string
}

variable "worker_task_role_arn" {
  type = string
}

# --- Runtime configuration ---

variable "backend_environment" {
  description = "Plain (non-secret) environment variables for the backend API container."
  type        = map(string)
  default     = {}
}

variable "backend_secrets" {
  description = "Secret environment variables for the backend API container: env var name -> Secrets Manager/SSM ARN."
  type        = map(string)
  default     = {}
}

variable "worker_environment" {
  description = "Plain (non-secret) environment variables shared by both worker containers (telemetry consumer, simulator)."
  type        = map(string)
  default     = {}
}

variable "worker_secrets" {
  description = "Secret environment variables shared by both worker containers: env var name -> ARN."
  type        = map(string)
  default     = {}
}

variable "tags" {
  type    = map(string)
  default = {}
}
