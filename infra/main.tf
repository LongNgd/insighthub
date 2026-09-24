locals {
  name      = "insighthub-prod"
  namespace = "insighthub-prod"
  tags = {
    project     = "insighthub"
    environment = "prod"
    owner       = var.owner
    cost_center = var.cost_center
    managed_by  = "terraform"
    Class       = "DO2603"
    LabId       = var.lab_id
    Owner       = var.owner
    ExpiresAt   = var.expires_at
  }
}

# The VPC and private subnets are existing, inventoried lab inputs.
data "aws_vpc" "lab" {
  id = var.vpc_id
}

data "aws_subnet" "private" {
  for_each = toset(var.private_subnet_ids)
  id       = each.value
}

resource "aws_iam_role" "eks_cluster" {
  name = "${local.name}-cluster"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "eks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_iam_role" "eks_nodes" {
  name = "${local.name}-nodes"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "node_worker" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "node_cni" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "node_ecr" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPullOnly"
}

resource "aws_kms_key" "lab" {
  description             = "EKS, logs, RDS, Redis and secrets encryption for ${local.name}"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableAccountIamPolicies"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${var.aws_account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "AllowEksLogEncryption"
        Effect    = "Allow"
        Principal = { Service = "logs.${var.aws_region}.amazonaws.com" }
        Action    = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"]
        Resource  = "*"
        Condition = {
          ArnEquals = {
            "kms:EncryptionContext:aws:logs:arn" = [
              "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/eks/${local.name}/cluster",
              "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${local.name}-redis-rotation",
            ]
          }
        }
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "eks" {
  name              = "/aws/eks/${local.name}/cluster"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.lab.arn
}

resource "aws_eks_cluster" "this" {
  name                      = local.name
  role_arn                  = aws_iam_role.eks_cluster.arn
  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  vpc_config {
    subnet_ids              = var.private_subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = false
  }

  encryption_config {
    provider {
      key_arn = aws_kms_key.lab.arn
    }
    resources = ["secrets"]
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster, aws_cloudwatch_log_group.eks]
}

resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${local.name}-nodes"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = [var.node_instance_type]

  scaling_config {
    desired_size = 2
    min_size     = 1
    max_size     = 2
  }

  depends_on = [
    aws_iam_role_policy_attachment.node_worker,
    aws_iam_role_policy_attachment.node_cni,
    aws_iam_role_policy_attachment.node_ecr,
  ]
}

resource "aws_security_group" "rds" {
  name        = "${local.name}-rds"
  description = "PostgreSQL access from EKS nodes only"
  vpc_id      = data.aws_vpc.lab.id
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_eks" {
  description                  = "PostgreSQL from InsightHub EKS nodes"
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_db_subnet_group" "this" {
  name       = "${local.name}-db"
  subnet_ids = var.private_subnet_ids

  lifecycle {
    precondition {
      condition = (
        length(distinct([for subnet in data.aws_subnet.private : subnet.availability_zone])) >= 2 &&
        alltrue([for subnet in data.aws_subnet.private : subnet.vpc_id == data.aws_vpc.lab.id])
      )
      error_message = "Private subnets must belong to the lab VPC and span at least two availability zones."
    }
  }
}

resource "aws_db_parameter_group" "postgres" {
  name   = "${local.name}-postgres16"
  family = "postgres16"

  parameter {
    name  = "log_statement"
    value = "ddl"
  }

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}

resource "aws_iam_role" "rds_monitoring" {
  name = "${local.name}-rds-monitoring"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "monitoring.rds.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

resource "aws_db_instance" "this" {
  identifier                          = "${local.name}-postgres"
  engine                              = "postgres"
  engine_version                      = "16"
  instance_class                      = var.db_instance_class
  allocated_storage                   = 20
  storage_type                        = "gp3"
  storage_encrypted                   = true
  db_name                             = "insighthub"
  username                            = "insighthub_admin"
  manage_master_user_password         = true
  kms_key_id                          = aws_kms_key.lab.arn
  iam_database_authentication_enabled = true
  db_subnet_group_name                = aws_db_subnet_group.this.name
  parameter_group_name                = aws_db_parameter_group.postgres.name
  vpc_security_group_ids              = [aws_security_group.rds.id]
  publicly_accessible                 = false
  multi_az                            = true
  backup_retention_period             = 7
  copy_tags_to_snapshot               = true
  auto_minor_version_upgrade          = true
  enabled_cloudwatch_logs_exports     = ["postgresql", "upgrade"]
  performance_insights_enabled        = true
  performance_insights_kms_key_id     = aws_kms_key.lab.arn
  monitoring_interval                 = 60
  monitoring_role_arn                 = aws_iam_role.rds_monitoring.arn
  deletion_protection                 = var.rds_deletion_protection
  skip_final_snapshot                 = true # Lab dataset is reproducible; do not retain a billable snapshot.

  depends_on = [aws_iam_role_policy_attachment.rds_monitoring]
}

resource "aws_security_group" "redis" {
  name        = "${local.name}-redis"
  description = "Redis access from EKS nodes only"
  vpc_id      = data.aws_vpc.lab.id
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_eks" {
  description                  = "Redis from InsightHub EKS nodes"
  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
}

resource "aws_elasticache_subnet_group" "this" {
  name       = "${local.name}-cache"
  subnet_ids = var.private_subnet_ids

  lifecycle {
    precondition {
      condition = (
        length(distinct([for subnet in data.aws_subnet.private : subnet.availability_zone])) >= 2 &&
        alltrue([for subnet in data.aws_subnet.private : subnet.vpc_id == data.aws_vpc.lab.id])
      )
      error_message = "Redis private subnets must belong to the lab VPC and span at least two availability zones."
    }
  }
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id       = "${local.name}-redis"
  description                = "InsightHub bounded lab Redis"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.cache_node_type
  num_cache_clusters         = 2
  automatic_failover_enabled = true
  multi_az_enabled           = true
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  kms_key_id                 = aws_kms_key.lab.arn
  auth_token                 = var.redis_auth_token
  snapshot_retention_limit   = 0

  # Secrets Manager rotation changes the remote token after bootstrap.
  lifecycle {
    ignore_changes = [auth_token]
  }
}

resource "aws_secretsmanager_secret" "redis" {
  name                    = "${local.name}/redis-auth"
  description             = "Redis AUTH token for the InsightHub lab"
  kms_key_id              = aws_kms_key.lab.arn
  recovery_window_in_days = 0
}

# Secret values still reside in Terraform state; protect the S3 state and any plan files.
resource "aws_secretsmanager_secret_version" "redis" {
  secret_id     = aws_secretsmanager_secret.redis.id
  secret_string = var.redis_auth_token

  # Rotation owns subsequent versions; Terraform only bootstraps the initial token.
  lifecycle {
    ignore_changes = [secret_string]
  }
}

data "tls_certificate" "eks_oidc" {
  url = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks_oidc.certificates[0].sha1_fingerprint]
}

resource "aws_iam_role" "insighthub" {
  name = "${local.name}-workload"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = "sts:AssumeRoleWithWebIdentity"
      Principal = {
        Federated = aws_iam_openid_connect_provider.eks.arn
      }
      Condition = {
        StringEquals = {
          "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:aud" = "sts.amazonaws.com"
          "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub" = "system:serviceaccount:${local.namespace}:insighthub"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "read_secrets" {
  name = "${local.name}-read-secrets"
  role = aws_iam_role.insighthub.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.redis.arn]
    }]
  })
}

resource "kubernetes_namespace_v1" "insighthub" {
  count = var.manage_namespace ? 1 : 0

  metadata {
    name = local.namespace
    labels = {
      app        = "insighthub"
      managed_by = "terraform"
    }
  }

  depends_on = [aws_eks_node_group.this]
}

resource "kubernetes_service_account_v1" "insighthub" {
  count = var.manage_namespace ? 1 : 0

  metadata {
    name      = "insighthub"
    namespace = kubernetes_namespace_v1.insighthub[0].metadata[0].name
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.insighthub.arn
    }
  }
}
