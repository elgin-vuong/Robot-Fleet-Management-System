# Amazon MSK — only created when enable_kafka = true (default false; see
# variables.tf and README "Kafka / event streaming" for why). Local
# development is unaffected either way: it keeps using the Kafka container
# in the repo's root docker-compose.yml.
module "messaging" {
  count  = var.enable_kafka ? 1 : 0
  source = "./modules/messaging"

  name_prefix          = local.name_prefix
  subnet_ids           = module.networking.data_subnet_ids
  security_group_id    = module.security.msk_sg_id
  broker_instance_type = var.kafka_broker_instance_type
  broker_count         = var.kafka_broker_count
  ebs_volume_size      = var.kafka_ebs_volume_size
  tags                 = local.common_tags
}
