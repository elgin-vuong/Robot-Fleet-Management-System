module "monitoring" {
  source = "./modules/monitoring"

  name_prefix                     = local.name_prefix
  alarm_email                     = var.alarm_email
  ecs_cluster_name                = module.compute.cluster_name
  backend_service_name            = module.compute.backend_service_name
  alb_arn_suffix                  = module.compute.alb_arn_suffix
  backend_target_group_arn_suffix = module.compute.backend_target_group_arn_suffix
  rds_instance_id                 = "${local.name_prefix}-postgres"
  tags                            = local.common_tags
}
