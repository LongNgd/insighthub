module "insighthub_production" {
  source = "./modules/insighthub-production"

  cluster_name                = var.eks_cluster_name
  cluster_oidc_issuer_url     = data.aws_eks_cluster.this.identity[0].oidc[0].issuer
  cluster_oidc_provider_arn   = data.aws_iam_openid_connect_provider.this.arn
  namespace                   = "insighthub"
  vpc_id                      = var.vpc_id
  private_subnet_ids          = var.private_subnet_ids
  workload_security_group_ids = var.workload_security_group_ids
  permissions_boundary_arn    = var.permissions_boundary_arn
  kms_key_arn                 = var.kms_key_arn
  deletion_protection         = var.deletion_protection
  skip_final_snapshot         = var.skip_final_snapshot

  tags = {
    project     = var.project
    environment = var.environment
    owner       = var.owner
    cost_center = var.cost_center
  }
}
