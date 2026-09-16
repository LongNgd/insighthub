data "aws_region" "current" {}

locals {
  name_prefix = substr("${var.tags.project}-${var.tags.environment}", 0, 24)
  common_tags = merge(var.tags, {
    managed_by = "terraform"
    cluster    = var.cluster_name
  })

  oidc_provider_hostpath = trimprefix(var.cluster_oidc_issuer_url, "https://")
  kms_key_arn            = var.kms_key_arn != null ? var.kms_key_arn : aws_kms_key.this[0].arn
  pgvector_bootstrap_sql = "CREATE EXTENSION IF NOT EXISTS vector;"
}
