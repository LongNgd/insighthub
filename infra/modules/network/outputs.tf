output "vpc_id" {
  description = "InsightHub VPC ID."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs for internet-facing load balancers and NAT."
  value       = [for az in var.availability_zones : aws_subnet.public[az].id]
}

output "private_subnet_ids" {
  description = "Private subnet IDs for EKS nodes, RDS, and Redis."
  value       = [for az in var.availability_zones : aws_subnet.private[az].id]
}
