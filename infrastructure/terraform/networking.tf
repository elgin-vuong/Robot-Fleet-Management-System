module "networking" {
  source = "./modules/networking"

  name_prefix         = local.name_prefix
  vpc_cidr            = var.vpc_cidr
  azs                 = local.azs
  public_subnet_cidrs = local.public_subnet_cidrs
  app_subnet_cidrs    = local.app_subnet_cidrs
  data_subnet_cidrs   = local.data_subnet_cidrs
  nat_strategy        = var.nat_strategy
  tags                = local.common_tags
}
