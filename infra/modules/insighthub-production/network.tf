resource "aws_security_group" "rds" {
  name_prefix            = "${local.name_prefix}-rds-"
  description            = "PostgreSQL access from InsightHub EKS workloads only"
  vpc_id                 = var.vpc_id
  revoke_rules_on_delete = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-rds"
  })
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_workload" {
  for_each = var.workload_security_group_ids

  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = each.value
  description                  = "PostgreSQL from EKS workload security group ${each.value}"
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"

  tags = local.common_tags
}

resource "aws_security_group" "redis" {
  name_prefix            = "${local.name_prefix}-redis-"
  description            = "Redis access from InsightHub EKS workloads only"
  vpc_id                 = var.vpc_id
  revoke_rules_on_delete = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis"
  })
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_workload" {
  for_each = var.workload_security_group_ids

  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = each.value
  description                  = "Redis from EKS workload security group ${each.value}"
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"

  tags = local.common_tags
}
