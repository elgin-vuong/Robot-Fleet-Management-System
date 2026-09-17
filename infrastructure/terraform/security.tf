module "security" {
  source = "./modules/security"

  name_prefix  = local.name_prefix
  vpc_id       = module.networking.vpc_id
  enable_kafka = var.enable_kafka
  tags         = local.common_tags
}
