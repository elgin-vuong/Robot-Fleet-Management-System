resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = var.enable_container_insights ? "enabled" : "disabled"
  }

  tags = var.tags
}

# One log group per logical service — kept here (not in the monitoring
# module) since they're tightly coupled to the task definitions that
# reference them by name.
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${var.name_prefix}/backend"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/${var.name_prefix}/frontend"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "telemetry_consumer" {
  count             = var.enable_telemetry_consumer ? 1 : 0
  name              = "/ecs/${var.name_prefix}/telemetry-consumer"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "simulator" {
  count             = var.enable_simulator_worker ? 1 : 0
  name              = "/ecs/${var.name_prefix}/simulator"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}
