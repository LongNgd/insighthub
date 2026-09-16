output "namespace" {
  description = "Kubernetes namespace managed by the module."
  value       = module.insighthub_production.namespace
}

output "service_account_name" {
  description = "IRSA-enabled Kubernetes ServiceAccount name."
  value       = module.insighthub_production.service_account_name
}

output "irsa_role_arn" {
  description = "Least-privilege IAM role assumed by the InsightHub ServiceAccount."
  value       = module.insighthub_production.irsa_role_arn
}

output "rds_endpoint" {
  description = "Private PostgreSQL endpoint."
  value       = module.insighthub_production.rds_endpoint
}

output "rds_master_secret_arn" {
  description = "RDS-managed master credential secret ARN."
  value       = module.insighthub_production.rds_master_secret_arn
}

output "redis_primary_endpoint" {
  description = "Private TLS Redis primary endpoint."
  value       = module.insighthub_production.redis_primary_endpoint
}

output "redis_secret_arn" {
  description = "Secrets Manager ARN containing the Redis connection details."
  value       = module.insighthub_production.redis_secret_arn
}

output "pgvector_bootstrap_sql" {
  description = "Idempotent statement that the deployment migration job must execute against RDS."
  value       = module.insighthub_production.pgvector_bootstrap_sql
}
