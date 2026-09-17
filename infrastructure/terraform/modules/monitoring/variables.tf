variable "name_prefix" {
  type = string
}

variable "alarm_email" {
  description = "Optional email to subscribe to the alarm SNS topic. Empty string = no subscription created."
  type        = string
  default     = ""
}

variable "ecs_cluster_name" {
  type = string
}

variable "backend_service_name" {
  type = string
}

variable "alb_arn_suffix" {
  description = "The `arn_suffix` attribute of the ALB (short form CloudWatch needs for its dimensions, not the full ARN)."
  type        = string
}

variable "backend_target_group_arn_suffix" {
  type = string
}

variable "rds_instance_id" {
  type = string
}

variable "cpu_alarm_threshold" {
  type    = number
  default = 80
}

variable "memory_alarm_threshold" {
  type    = number
  default = 80
}

variable "tags" {
  type    = map(string)
  default = {}
}
