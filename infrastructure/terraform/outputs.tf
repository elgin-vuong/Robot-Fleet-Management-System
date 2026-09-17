output "alb_dns_name" {
  description = "Public DNS name of the ALB. Use this to reach the app if domain_name is not set."
  value       = module.compute.alb_dns_name
}

output "app_url" {
  description = "Best-guess URL for the app: the custom domain if set, otherwise the ALB's DNS name over HTTP."
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "http://${module.compute.alb_dns_name}"
}

output "ecs_cluster_name" {
  value = module.compute.cluster_name
}

output "ecr_backend_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_repository_url" {
  value = aws_ecr_repository.frontend.repository_url
}

output "rds_endpoint" {
  description = "host:port — connect via Secrets Manager for credentials, never hardcode them."
  value       = module.database.endpoint
}

output "redis_primary_endpoint" {
  value = module.cache.primary_endpoint_address
}

output "kafka_bootstrap_brokers" {
  description = "null when enable_kafka = false."
  value       = var.enable_kafka ? module.messaging[0].bootstrap_brokers_tls : null
}

output "s3_bucket_name" {
  value = module.storage.bucket_id
}

output "vpc_id" {
  value = module.networking.vpc_id
}

output "github_actions_deploy_role_arn" {
  description = "Set this as the AWS role ARN GitHub Actions assumes via OIDC (see README CI/CD section)."
  value       = aws_iam_role.github_actions_deploy.arn
}

output "db_credentials_secret_arn" {
  value = aws_secretsmanager_secret.db_credentials.arn
}

output "ai_api_key_secret_arn" {
  description = "Populate this secret's value after apply — see README 'Secrets management'."
  value       = aws_secretsmanager_secret.ai_api_key.arn
}

output "voyage_api_key_secret_arn" {
  description = "Populate this secret's value after apply — see README 'Secrets management'."
  value       = aws_secretsmanager_secret.voyage_api_key.arn
}
