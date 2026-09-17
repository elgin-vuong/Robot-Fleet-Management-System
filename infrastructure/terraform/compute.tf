locals {
  # ACM certificate for HTTPS is only wired up when a domain is supplied —
  # see acm.tf. Otherwise the ALB serves plain HTTP on its AWS DNS name.
  certificate_arn = var.domain_name != "" ? aws_acm_certificate_validation.main[0].certificate_arn : null

  # Workers are useless (and would crash-loop) without a reachable Kafka —
  # gate both on enable_kafka, not just the separate simulator toggle.
  enable_telemetry_consumer = var.enable_kafka
  enable_simulator_worker   = var.enable_kafka && var.enable_simulator_worker

  # REDIS_URL: when transit encryption is on, the whole rediss://... URL
  # (including the AUTH token) is a secret. When it's off, there's no
  # secret involved at all — it's just a plain endpoint.
  redis_url_plain = var.redis_transit_encryption_enabled ? null : "redis://${module.cache.primary_endpoint_address}:${module.cache.port}"

  backend_environment = merge(
    {},
    var.enable_kafka ? {} : {}, # backend API never talks to Kafka directly; nothing to add here regardless
    local.redis_url_plain != null ? { REDIS_URL = local.redis_url_plain } : {}
  )

  backend_secrets = merge(
    {
      DATABASE_URL   = "${aws_secretsmanager_secret.db_credentials.arn}:url::"
      JWT_SECRET_KEY = aws_secretsmanager_secret.jwt_secret.arn
      AI_API_KEY     = aws_secretsmanager_secret.ai_api_key.arn
      VOYAGE_API_KEY = aws_secretsmanager_secret.voyage_api_key.arn
    },
    var.redis_transit_encryption_enabled ? { REDIS_URL = "${aws_secretsmanager_secret.redis_auth[0].arn}:url::" } : {}
  )

  worker_environment = merge(
    {},
    var.enable_kafka ? {
      KAFKA_BOOTSTRAP_SERVERS = module.messaging[0].bootstrap_brokers_tls
      KAFKA_SECURITY_PROTOCOL = "SSL"
    } : {},
    local.redis_url_plain != null ? { REDIS_URL = local.redis_url_plain } : {}
  )

  worker_secrets = merge(
    { DATABASE_URL = "${aws_secretsmanager_secret.db_credentials.arn}:url::" },
    var.redis_transit_encryption_enabled ? { REDIS_URL = "${aws_secretsmanager_secret.redis_auth[0].arn}:url::" } : {}
  )
}

module "compute" {
  source = "./modules/compute"

  name_prefix       = local.name_prefix
  vpc_id            = module.networking.vpc_id
  public_subnet_ids = module.networking.public_subnet_ids
  app_subnet_ids    = module.networking.app_subnet_ids

  alb_sg_id      = module.security.alb_sg_id
  backend_sg_id  = module.security.backend_sg_id
  frontend_sg_id = module.security.frontend_sg_id
  worker_sg_id   = module.security.worker_sg_id

  certificate_arn = local.certificate_arn

  log_retention_days = var.log_retention_days

  backend_image         = aws_ecr_repository.backend.repository_url
  backend_image_tag     = var.backend_image_tag
  frontend_image        = aws_ecr_repository.frontend.repository_url
  frontend_image_tag    = var.frontend_image_tag
  backend_path_patterns = local.backend_path_patterns

  backend_cpu            = var.backend_cpu
  backend_memory         = var.backend_memory
  backend_desired_count  = var.backend_desired_count
  frontend_cpu           = var.frontend_cpu
  frontend_memory        = var.frontend_memory
  frontend_desired_count = var.frontend_desired_count
  worker_cpu             = var.worker_cpu
  worker_memory          = var.worker_memory

  enable_telemetry_consumer = local.enable_telemetry_consumer
  enable_simulator_worker   = local.enable_simulator_worker

  task_execution_role_arn = aws_iam_role.ecs_task_execution.arn
  backend_task_role_arn   = aws_iam_role.backend_task.arn
  worker_task_role_arn    = aws_iam_role.worker_task.arn

  backend_environment = local.backend_environment
  backend_secrets     = local.backend_secrets
  worker_environment  = local.worker_environment
  worker_secrets      = local.worker_secrets

  tags = local.common_tags
}
