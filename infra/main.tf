locals {
  namespace = "insighthub-${var.environment}"
  availability_zones = slice(
    data.aws_availability_zones.available.names,
    0,
    2,
  )
  tags = {
    project     = var.project
    environment = var.environment
    owner       = var.owner
    cost_center = var.cost_center
  }
}

module "network" {
  source = "./modules/network"

  name               = "${var.project}-${var.environment}"
  vpc_cidr           = var.vpc_cidr
  availability_zones = local.availability_zones
  cluster_name       = var.eks_cluster_name
  tags               = local.tags
}

module "eks" {
  source = "./modules/eks"

  cluster_name             = var.eks_cluster_name
  kubernetes_version       = var.kubernetes_version
  private_subnet_ids       = module.network.private_subnet_ids
  public_access_cidrs      = var.eks_public_access_cidrs
  node_instance_types      = var.eks_node_instance_types
  permissions_boundary_arn = var.permissions_boundary_arn
  tags                     = local.tags
}

module "insighthub_production" {
  source = "./modules/insighthub-production"

  cluster_name              = module.eks.cluster_name
  cluster_oidc_issuer_url   = module.eks.oidc_issuer_url
  cluster_oidc_provider_arn = module.eks.oidc_provider_arn
  namespace                 = local.namespace
  vpc_id                    = module.network.vpc_id
  private_subnet_ids        = module.network.private_subnet_ids
  workload_security_groups = {
    eks_cluster = module.eks.cluster_security_group_id
  }
  permissions_boundary_arn = var.permissions_boundary_arn
  kms_key_arn              = var.kms_key_arn
  deletion_protection      = var.deletion_protection
  skip_final_snapshot      = var.skip_final_snapshot

  depends_on = [module.eks]

  tags = local.tags
}
