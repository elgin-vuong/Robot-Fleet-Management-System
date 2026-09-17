variable "name_prefix" {
  type = string
}

variable "data_subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "engine_version" {
  type = string
}

variable "instance_class" {
  type = string
}

variable "allocated_storage" {
  type = number
}

variable "max_allocated_storage" {
  type = number
}

variable "db_name" {
  type = string
}

variable "db_username" {
  type = string
}

variable "multi_az" {
  type = bool
}

variable "deletion_protection" {
  type = bool
}

variable "skip_final_snapshot" {
  type = bool
}

variable "backup_retention_days" {
  type = number
}

variable "tags" {
  type    = map(string)
  default = {}
}
