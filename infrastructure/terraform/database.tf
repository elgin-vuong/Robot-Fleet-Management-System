module "database" {
  source = "./modules/database"

  name_prefix           = local.name_prefix
  data_subnet_ids       = module.networking.data_subnet_ids
  security_group_id     = module.security.rds_sg_id
  engine_version        = var.db_engine_version
  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  db_name               = var.db_name
  db_username           = var.db_username
  multi_az              = var.db_multi_az
  deletion_protection   = var.db_deletion_protection
  skip_final_snapshot   = var.db_skip_final_snapshot
  backup_retention_days = var.db_backup_retention_days
  tags                  = local.common_tags
}
