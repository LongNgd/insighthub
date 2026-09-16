output "namespace" {
  description = "Kubernetes namespace name."
  value       = kubernetes_namespace_v1.this.metadata[0].name
}

output "service_account_name" {
  description = "IRSA-enabled Kubernetes ServiceAccount name."
  value       = kubernetes_service_account_v1.this.metadata[0].name
}

output "irsa_role_arn" {
  description = "IAM role ARN trusted only by the InsightHub ServiceAccount."
  value       = aws_iam_role.workload.arn
}

output "kms_key_arn" {
  description = "KMS key used for RDS, ElastiCache, and Secrets Manager encryption."
  value       = local.kms_key_arn
}

output "rds_endpoint" {
  description = "Private RDS PostgreSQL endpoint without credentials."
  value       = aws_db_instance.this.address
}

output "rds_port" {
  description = "PostgreSQL port."
  value       = aws_db_instance.this.port
}

output "rds_master_secret_arn" {
  description = "RDS-managed Secrets Manager ARN containing the master credentials."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}

output "rds_security_group_id" {
  description = "Security group allowing PostgreSQL only from configured workload security groups."
  value       = aws_security_group.rds.id
}

output "redis_primary_endpoint" {
  description = "Private Redis TLS primary endpoint."
  value       = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "redis_port" {
  description = "Redis TLS port."
  value       = aws_elasticache_replication_group.this.port
}

output "redis_secret_arn" {
  description = "Secrets Manager ARN containing the Redis token and endpoint."
  value       = aws_secretsmanager_secret.redis.arn
}

output "redis_security_group_id" {
  description = "Security group allowing Redis only from configured workload security groups."
  value       = aws_security_group.redis.id
}

output "pgvector_bootstrap_sql" {
  description = "Idempotent pgvector extension statement stored in the namespace bootstrap ConfigMap."
  value       = local.pgvector_bootstrap_sql
}
