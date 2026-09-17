variable "name_prefix" {
  type = string
}

variable "data_subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "node_type" {
  type = string
}

variable "engine_version" {
  type = string
}

variable "replica_count" {
  type = number
}

variable "transit_encryption_enabled" {
  type = bool
}

variable "tags" {
  type    = map(string)
  default = {}
}
