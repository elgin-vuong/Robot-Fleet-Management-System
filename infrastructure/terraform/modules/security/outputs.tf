output "alb_sg_id" {
  value = aws_security_group.alb.id
}

output "backend_sg_id" {
  value = aws_security_group.backend.id
}

output "frontend_sg_id" {
  value = aws_security_group.frontend.id
}

output "worker_sg_id" {
  value = aws_security_group.worker.id
}

output "rds_sg_id" {
  value = aws_security_group.rds.id
}

output "redis_sg_id" {
  value = aws_security_group.redis.id
}

output "msk_sg_id" {
  description = "null when enable_kafka = false."
  value       = length(aws_security_group.msk) > 0 ? aws_security_group.msk[0].id : null
}
