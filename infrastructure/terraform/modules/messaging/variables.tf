variable "name_prefix" {
  type = string
}

variable "subnet_ids" {
  description = "Subnets to place broker ENIs in (one AZ per broker, cycling if broker_count > number of subnets)."
  type        = list(string)
}

variable "security_group_id" {
  type = string
}

variable "broker_instance_type" {
  type = string
}

variable "broker_count" {
  type = number
}

variable "ebs_volume_size" {
  type = number
}

variable "kafka_version" {
  description = "MSK-supported Apache Kafka version."
  type        = string
  default     = "3.6.0"
}

variable "tags" {
  type    = map(string)
  default = {}
}
