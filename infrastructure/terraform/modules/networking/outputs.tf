output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.main.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC."
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets (ALB, NAT Gateways)."
  value       = aws_subnet.public[*].id
}

output "app_subnet_ids" {
  description = "IDs of the private application subnets (ECS Fargate tasks)."
  value       = aws_subnet.app[*].id
}

output "data_subnet_ids" {
  description = "IDs of the private data subnets (RDS, ElastiCache, MSK)."
  value       = aws_subnet.data[*].id
}

output "nat_gateway_ids" {
  description = "IDs of any NAT Gateways created (empty list if nat_strategy = \"none\")."
  value       = aws_nat_gateway.main[*].id
}
