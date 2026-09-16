resource "kubernetes_namespace_v1" "this" {
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/name"       = var.tags.project
      "app.kubernetes.io/managed-by" = "terraform"
      environment                    = var.tags.environment
    }
  }
}

resource "kubernetes_service_account_v1" "this" {
  metadata {
    name      = var.service_account_name
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.workload.arn
    }
    labels = {
      "app.kubernetes.io/name"       = var.tags.project
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }

  automount_service_account_token = true
}

resource "kubernetes_config_map_v1" "database_bootstrap" {
  metadata {
    name      = "insighthub-database-bootstrap"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels = {
      "app.kubernetes.io/name"       = var.tags.project
      "app.kubernetes.io/component"  = "database-migration"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }

  data = {
    "001-enable-pgvector.sql" = local.pgvector_bootstrap_sql
  }
}
