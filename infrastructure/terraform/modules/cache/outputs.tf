output "primary_endpoint_address" {
  value = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "port" {
  value = aws_elasticache_replication_group.main.port
}

output "auth_token" {
  value     = var.transit_encryption_enabled ? random_password.auth_token[0].result : null
  sensitive = true
}

output "transit_encryption_enabled" {
  value = var.transit_encryption_enabled
}
