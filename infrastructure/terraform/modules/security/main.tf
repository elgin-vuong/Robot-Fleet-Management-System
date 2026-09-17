########################################
# ALB — the only security group that accepts traffic from the public internet.
########################################

resource "aws_security_group" "alb" {
  name_prefix = "${var.name_prefix}-alb-"
  description = "Public ALB: accepts HTTP/HTTPS from the internet."
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP from internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "To backend/frontend ECS tasks"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

########################################
# Backend API tasks
########################################

resource "aws_security_group" "backend" {
  name_prefix = "${var.name_prefix}-backend-"
  description = "Backend FastAPI ECS tasks: accepts traffic from the ALB only."
  vpc_id      = var.vpc_id

  ingress {
    description     = "From ALB"
    from_port       = var.backend_container_port
    to_port         = var.backend_container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Outbound to RDS/Redis/MSK/internet (ECR pulls, Anthropic/Voyage AI APIs)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-backend-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

########################################
# Frontend (Nginx) tasks
########################################

resource "aws_security_group" "frontend" {
  name_prefix = "${var.name_prefix}-frontend-"
  description = "Frontend Nginx ECS tasks: accepts traffic from the ALB only."
  vpc_id      = var.vpc_id

  ingress {
    description     = "From ALB"
    from_port       = var.frontend_container_port
    to_port         = var.frontend_container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Outbound for ECR pulls"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-frontend-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

########################################
# Background worker tasks (telemetry consumer, simulator) — no ALB target,
# but they need the same egress reach as the backend (Postgres, Redis, Kafka,
# ECR, internet).
########################################

resource "aws_security_group" "worker" {
  name_prefix = "${var.name_prefix}-worker-"
  description = "Background worker ECS tasks (telemetry consumer, simulator). No inbound traffic expected."
  vpc_id      = var.vpc_id

  egress {
    description = "Outbound to RDS/Redis/MSK/internet"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-worker-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

########################################
# RDS PostgreSQL — private, no egress needed, ingress only from app-tier SGs.
########################################

resource "aws_security_group" "rds" {
  name_prefix = "${var.name_prefix}-rds-"
  description = "RDS PostgreSQL: reachable only from backend and worker tasks. No internet access in or out."
  vpc_id      = var.vpc_id

  ingress {
    description     = "Postgres from backend"
    from_port       = var.db_port
    to_port         = var.db_port
    protocol        = "tcp"
    security_groups = [aws_security_group.backend.id, aws_security_group.worker.id]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-rds-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

########################################
# ElastiCache Redis — private, ingress only from app-tier SGs.
########################################

resource "aws_security_group" "redis" {
  name_prefix = "${var.name_prefix}-redis-"
  description = "ElastiCache Redis: reachable only from backend and worker tasks. No internet access in or out."
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis from backend"
    from_port       = var.redis_port
    to_port         = var.redis_port
    protocol        = "tcp"
    security_groups = [aws_security_group.backend.id, aws_security_group.worker.id]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-redis-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

########################################
# MSK Kafka brokers — only created when enable_kafka = true. Private,
# ingress only from app-tier SGs, on the plaintext and TLS broker ports.
########################################

resource "aws_security_group" "msk" {
  count       = var.enable_kafka ? 1 : 0
  name_prefix = "${var.name_prefix}-msk-"
  description = "MSK Kafka brokers: reachable only from backend and worker tasks. No internet access in or out."
  vpc_id      = var.vpc_id

  dynamic "ingress" {
    for_each = var.kafka_ports
    content {
      description     = "Kafka broker port ${ingress.value} from app tier"
      from_port       = ingress.value
      to_port         = ingress.value
      protocol        = "tcp"
      security_groups = [aws_security_group.backend.id, aws_security_group.worker.id]
    }
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-msk-sg" })

  lifecycle {
    create_before_destroy = true
  }
}
