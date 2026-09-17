variable "name_prefix" {
  description = "Prefix for resource names, e.g. \"robot-fleet-dev\"."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
}

variable "azs" {
  description = "List of Availability Zone names to use, one subnet of each tier per AZ."
  type        = list(string)
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets, one per AZ (same order as var.azs)."
  type        = list(string)
}

variable "app_subnet_cidrs" {
  description = "CIDR blocks for private application subnets, one per AZ."
  type        = list(string)
}

variable "data_subnet_cidrs" {
  description = "CIDR blocks for private data subnets, one per AZ."
  type        = list(string)
}

variable "nat_strategy" {
  description = "\"single\", \"one_per_az\", or \"none\" — see root variables.tf for tradeoffs."
  type        = string
}

variable "tags" {
  description = "Common tags applied to every resource."
  type        = map(string)
  default     = {}
}
