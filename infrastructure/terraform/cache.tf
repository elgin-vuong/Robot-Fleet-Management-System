module "cache" {
  source = "./modules/cache"

  name_prefix                = local.name_prefix
  data_subnet_ids            = module.networking.data_subnet_ids
  security_group_id          = module.security.redis_sg_id
  node_type                  = var.redis_node_type
  engine_version             = var.redis_engine_version
  replica_count              = var.redis_replica_count
  transit_encryption_enabled = var.redis_transit_encryption_enabled
  tags                       = local.common_tags
}
