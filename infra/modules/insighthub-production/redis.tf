resource "random_password" "redis_auth" {
  length           = 48
  special          = true
  override_special = "!&#$^<>-"
}

resource "aws_elasticache_subnet_group" "this" {
  name        = "${local.name_prefix}-redis"
  subnet_ids  = sort(tolist(var.private_subnet_ids))
  description = "Private subnets for InsightHub Redis"

  tags = local.common_tags
}

resource "aws_elasticache_parameter_group" "redis7" {
  name        = "${local.name_prefix}-redis7"
  family      = "redis7"
  description = "InsightHub Redis 7 parameters"

  tags = local.common_tags
}

resource "aws_elasticache_replication_group" "this" {
  # checkov:skip=CKV2_AWS_50:Lab sizing explicitly requires one cache.t3.micro node without Multi-AZ failover.
  replication_group_id = "${local.name_prefix}-redis"
  description          = "InsightHub private encrypted Redis"

  engine               = "redis"
  engine_version       = var.redis_engine_version
  node_type            = var.redis_node_type
  port                 = 6379
  parameter_group_name = aws_elasticache_parameter_group.redis7.name
  subnet_group_name    = aws_elasticache_subnet_group.this.name
  security_group_ids   = [aws_security_group.redis.id]

  num_cache_clusters         = 1
  automatic_failover_enabled = false
  multi_az_enabled           = false

  at_rest_encryption_enabled = true
  kms_key_id                 = local.kms_key_arn
  transit_encryption_enabled = true
  transit_encryption_mode    = "required"
  auth_token                 = random_password.redis_auth.result

  snapshot_retention_limit   = 1
  snapshot_window            = "17:00-18:00"
  maintenance_window         = "sun:19:30-sun:20:30"
  apply_immediately          = false
  auto_minor_version_upgrade = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis"
  })
}

resource "aws_secretsmanager_secret" "redis" {
  # checkov:skip=CKV2_AWS_57:Automatic Redis token rotation requires coordinated ElastiCache/client rotation; this short-lived lab secret is destroyed after the run.
  name_prefix             = "${local.name_prefix}/redis-"
  description             = "InsightHub Redis TLS connection details"
  kms_key_id              = local.kms_key_arn
  recovery_window_in_days = 7

  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "redis" {
  secret_id = aws_secretsmanager_secret.redis.id
  secret_string = jsonencode({
    engine   = "redis"
    host     = aws_elasticache_replication_group.this.primary_endpoint_address
    port     = aws_elasticache_replication_group.this.port
    tls      = true
    password = random_password.redis_auth.result
  })
}
