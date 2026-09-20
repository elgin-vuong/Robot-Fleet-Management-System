locals {
  backend_env_list     = [for k, v in var.backend_environment : { name = k, value = v }]
  backend_secrets_list = [for k, v in var.backend_secrets : { name = k, valueFrom = v }]
  worker_env_list      = [for k, v in var.worker_environment : { name = k, value = v }]
  worker_secrets_list  = [for k, v in var.worker_secrets : { name = k, valueFrom = v }]

  backend_image_uri  = "${var.backend_image}:${var.backend_image_tag}"
  frontend_image_uri = "${var.frontend_image}:${var.frontend_image_tag}"
}

########################################
# Backend API service
########################################

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.name_prefix}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.backend_task_role_arn

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = local.backend_image_uri
      essential = true
      portMappings = [
        { containerPort = var.backend_container_port, protocol = "tcp" }
      ]
      environment = local.backend_env_list
      secrets     = local.backend_secrets_list
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "backend"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:${var.backend_container_port}/health')\" || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_service" "backend" {
  name            = "${var.name_prefix}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.backend_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.app_subnet_ids
    security_groups = [var.backend_sg_id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = var.backend_container_port
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  # Without this, a task definition that never passes the ALB health check
  # just sits there indefinitely — ECS keeps retrying placement forever,
  # and a CI step waiting on service stability would hang rather than fail.
  # With it: ECS gives up after enough failures, automatically reverts to
  # the last stable task definition, and the CI deploy step's
  # wait-for-service-stability fails promptly instead of hanging.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.http]

  lifecycle {
    ignore_changes = [task_definition] # allow CI to update the running task def without a plan diff on every apply
  }

  tags = var.tags
}

########################################
# Frontend service
########################################

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${var.name_prefix}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.frontend_cpu
  memory                   = var.frontend_memory
  execution_role_arn       = var.task_execution_role_arn

  container_definitions = jsonencode([
    {
      name      = "frontend"
      image     = local.frontend_image_uri
      essential = true
      portMappings = [
        { containerPort = var.frontend_container_port, protocol = "tcp" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.frontend.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "frontend"
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_service" "frontend" {
  name            = "${var.name_prefix}-frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.frontend_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.app_subnet_ids
    security_groups = [var.frontend_sg_id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = var.frontend_container_port
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.http]

  lifecycle {
    ignore_changes = [task_definition]
  }

  tags = var.tags
}

########################################
# Telemetry consumer worker — no ALB, no inbound traffic. Same backend
# image as the API, just a different container command.
########################################

resource "aws_ecs_task_definition" "telemetry_consumer" {
  count                    = var.enable_telemetry_consumer ? 1 : 0
  family                   = "${var.name_prefix}-telemetry-consumer"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.worker_task_role_arn

  container_definitions = jsonencode([
    {
      name        = "telemetry-consumer"
      image       = local.backend_image_uri
      essential   = true
      command     = ["python", "-m", "backend.app.consumers.telemetry_consumer"]
      environment = local.worker_env_list
      secrets     = local.worker_secrets_list
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.telemetry_consumer[0].name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "telemetry-consumer"
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_service" "telemetry_consumer" {
  count           = var.enable_telemetry_consumer ? 1 : 0
  name            = "${var.name_prefix}-telemetry-consumer"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.telemetry_consumer[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.app_subnet_ids
    security_groups = [var.worker_sg_id]
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  tags = var.tags
}

########################################
# Simulator worker — optional (var.enable_simulator_worker). Generates demo
# telemetry only; safe to disable or scale to 0.
########################################

resource "aws_ecs_task_definition" "simulator" {
  count                    = var.enable_simulator_worker ? 1 : 0
  family                   = "${var.name_prefix}-simulator"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.worker_task_role_arn

  container_definitions = jsonencode([
    {
      name        = "simulator"
      image       = local.backend_image_uri
      essential   = true
      command     = ["python", "-m", "backend.simulator.run"]
      environment = local.worker_env_list
      secrets     = local.worker_secrets_list
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.simulator[0].name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "simulator"
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_service" "simulator" {
  count           = var.enable_simulator_worker ? 1 : 0
  name            = "${var.name_prefix}-simulator"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.simulator[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.app_subnet_ids
    security_groups = [var.worker_sg_id]
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  tags = var.tags
}

data "aws_region" "current" {}
