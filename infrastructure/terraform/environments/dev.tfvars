# Dev environment — optimized for low cost over availability/durability.
# Everything here is also the default in variables.tf; this file exists so
# `terraform plan -var-file=environments/dev.tfvars` is explicit and so
# staging.tfvars/prod.tfvars can be added later (README "Adding staging/prod")
# without touching this one.

project_name = "robot-fleet"
environment  = "dev"
aws_region   = "us-east-1"

vpc_cidr     = "10.0.0.0/16"
az_count     = 2
nat_strategy = "single"

domain_name = ""

enable_kafka = false

db_instance_class        = "db.t4g.micro"
db_multi_az              = false
db_deletion_protection   = false
db_skip_final_snapshot   = true
db_backup_retention_days = 3

redis_node_type                  = "cache.t4g.micro"
redis_replica_count              = 0
redis_transit_encryption_enabled = true

backend_cpu            = 256
backend_memory         = 512
backend_desired_count  = 1
frontend_cpu           = 256
frontend_memory        = 512
frontend_desired_count = 1
worker_cpu             = 256
worker_memory          = 512

enable_simulator_worker = true

log_retention_days = 14
alarm_email        = ""

backend_image_tag  = "latest"
frontend_image_tag = "latest"

github_repository = "OWNER/REPO"
