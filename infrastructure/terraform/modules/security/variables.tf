variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "backend_container_port" {
  description = "Port the FastAPI backend listens on inside its container."
  type        = number
  default     = 8000
}

variable "frontend_container_port" {
  description = "Port the frontend Nginx container listens on."
  type        = number
  default     = 80
}

variable "db_port" {
  type    = number
  default = 5432
}

variable "redis_port" {
  type    = number
  default = 6379
}

variable "enable_kafka" {
  type    = bool
  default = false
}

variable "kafka_ports" {
  description = "MSK broker ports to allow from app-tier security groups: 9092 (plaintext), 9094 (TLS)."
  type        = list(number)
  default     = [9092, 9094]
}

variable "tags" {
  type    = map(string)
  default = {}
}
