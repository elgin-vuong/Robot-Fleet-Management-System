locals {
  bucket_name = var.s3_bucket_name_override != "" ? var.s3_bucket_name_override : "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-${random_id.bucket_suffix.hex}"
}

module "storage" {
  source = "./modules/storage"

  bucket_name   = local.bucket_name
  force_destroy = !local.is_prod
  tags          = local.common_tags
}
