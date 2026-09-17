# Amazon MSK (managed Kafka). Only instantiated by the root module when
# var.enable_kafka = true — see root messaging.tf. Brokers live in private
# data subnets with no internet route; reachable only from the app-tier
# security groups on the broker ports.
#
# Encryption: TLS both between clients and brokers, and between brokers
# themselves (encryption_in_transit below). At-rest encryption uses AWS's
# default MSK-managed KMS key (no extra cost or key management for dev).
#
# Authentication: network isolation (private subnets + security groups) is
# the primary boundary here, same as RDS/Redis. MSK also supports SASL/SCRAM
# and IAM-based client authentication for stronger per-client auth in
# staging/prod — not enabled by default to keep the dev path simple; see
# README "Future production hardening tasks".

resource "aws_msk_configuration" "main" {
  name              = "${var.name_prefix}-msk-config"
  kafka_versions    = [var.kafka_version]
  server_properties = <<-PROPERTIES
    auto.create.topics.enable=true
    default.replication.factor=${min(var.broker_count, 3)}
    min.insync.replicas=1
  PROPERTIES
}

resource "aws_msk_cluster" "main" {
  cluster_name           = "${var.name_prefix}-kafka"
  kafka_version          = var.kafka_version
  number_of_broker_nodes = var.broker_count

  broker_node_group_info {
    instance_type   = var.broker_instance_type
    client_subnets  = var.subnet_ids
    security_groups = [var.security_group_id]

    storage_info {
      ebs_storage_info {
        volume_size = var.ebs_volume_size
      }
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.main.arn
    revision = aws_msk_configuration.main.latest_revision
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  enhanced_monitoring = "DEFAULT"

  tags = merge(var.tags, { Name = "${var.name_prefix}-kafka" })
}
