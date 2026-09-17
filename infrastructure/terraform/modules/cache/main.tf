# AUTH token requires transit encryption; only generate/require one when
# transit_encryption_enabled = true (default). Without an AUTH token the
# app connects with a bare redis:// URL and no password.
resource "random_password" "auth_token" {
  count   = var.transit_encryption_enabled ? 1 : 0
  length  = 32
  special = false # ElastiCache AUTH tokens don't allow most special characters
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.name_prefix}-redis-subnets"
  subnet_ids = var.data_subnet_ids

  tags = var.tags
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.name_prefix}-redis"
  description          = "Redis for ${var.name_prefix} (cache, agent confirmations/history, rate limiting, Kafka->WebSocket pub/sub bridge)"

  engine         = "redis"
  engine_version = var.engine_version
  node_type      = var.node_type
  port           = 6379

  num_cache_clusters = 1 + var.replica_count
  # Automatic failover requires at least one replica; skip it for a
  # single-node dev setup.
  automatic_failover_enabled = var.replica_count > 0

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [var.security_group_id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = var.transit_encryption_enabled
  auth_token                 = var.transit_encryption_enabled ? random_password.auth_token[0].result : null

  apply_immediately = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-redis" })
}
