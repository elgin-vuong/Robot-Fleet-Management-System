output "endpoint" {
  description = "Connection endpoint (host:port)."
  value       = aws_db_instance.main.endpoint
}

output "address" {
  description = "Host name only, without the port."
  value       = aws_db_instance.main.address
}

output "port" {
  value = aws_db_instance.main.port
}

output "db_name" {
  value = aws_db_instance.main.db_name
}

output "username" {
  value = aws_db_instance.main.username
}

output "password" {
  value     = random_password.db.result
  sensitive = true
}

output "instance_arn" {
  value = aws_db_instance.main.arn
}
