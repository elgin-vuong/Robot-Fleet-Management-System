variable "bucket_name" {
  description = "Globally-unique S3 bucket name (already resolved by the caller, e.g. via random_id)."
  type        = string
}

variable "force_destroy" {
  description = "Whether to allow Terraform to delete this bucket even if it still contains objects. true is convenient for dev; false is strongly recommended for staging/prod to prevent accidental data loss."
  type        = bool
  default     = false
}

variable "noncurrent_version_expiration_days" {
  description = "Days to retain noncurrent object versions before they're permanently deleted."
  type        = number
  default     = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
