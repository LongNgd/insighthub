output "namespace" {
  description = "Kubernetes namespace created during the second stage."
  value       = local.namespace
}

output "eks_cluster_name" {
  description = "EKS cluster name."
  value       = aws_eks_cluster.this.name
}

output "rds_address" {
  description = "Private PostgreSQL endpoint; no credentials included."
  value       = aws_db_instance.this.address
}

output "redis_address" {
  description = "Private Redis primary endpoint; no AUTH token included."
  value       = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "workload_role_arn" {
  description = "IRSA role for the insighthub ServiceAccount."
  value       = aws_iam_role.insighthub.arn
}
