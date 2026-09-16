resource "aws_db_subnet_group" "this" {
  name        = "${local.name_prefix}-postgres"
  subnet_ids  = sort(tolist(var.private_subnet_ids))
  description = "Private subnets for InsightHub PostgreSQL"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-postgres"
  })
}

resource "aws_db_parameter_group" "postgres16" {
  name_prefix = "${local.name_prefix}-postgres16-"
  family      = "postgres16"
  description = "InsightHub PostgreSQL 16 parameters"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "immediate"
  }

  tags = local.common_tags
}

resource "aws_db_instance" "this" {
  # checkov:skip=CKV_AWS_157:Lab sizing explicitly requires a single-AZ RDS instance.
  # checkov:skip=CKV_AWS_293:Deletion protection is configurable and defaults off so the time-boxed lab can be torn down.
  identifier = "${local.name_prefix}-postgres"

  engine         = "postgres"
  engine_version = var.postgres_engine_version
  instance_class = var.rds_instance_class
  db_name        = "insighthub"
  username       = "insighthub_admin"
  port           = 5432

  manage_master_user_password   = true
  master_user_secret_kms_key_id = local.kms_key_arn

  allocated_storage = var.rds_allocated_storage_gib
  storage_type      = "gp3"
  storage_encrypted = true
  kms_key_id        = local.kms_key_arn

  multi_az               = false
  publicly_accessible    = false
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.postgres16.name

  iam_database_authentication_enabled   = true
  performance_insights_enabled          = true
  performance_insights_kms_key_id       = local.kms_key_arn
  performance_insights_retention_period = 7

  backup_retention_period = var.rds_backup_retention_days
  backup_window           = "18:00-18:30"
  maintenance_window      = "sun:19:00-sun:19:30"
  copy_tags_to_snapshot   = true

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  auto_minor_version_upgrade      = true
  monitoring_interval             = 60
  monitoring_role_arn             = aws_iam_role.rds_monitoring.arn
  apply_immediately               = false
  deletion_protection             = var.deletion_protection
  skip_final_snapshot             = var.skip_final_snapshot
  final_snapshot_identifier       = var.skip_final_snapshot ? null : "${local.name_prefix}-final"
  delete_automated_backups        = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-postgres"
  })
}

data "aws_iam_policy_document" "rds_monitoring_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "rds_monitoring" {
  name                 = "${local.name_prefix}-rds-monitoring"
  description          = "Enhanced monitoring role for the InsightHub RDS instance"
  assume_role_policy   = data.aws_iam_policy_document.rds_monitoring_assume_role.json
  permissions_boundary = var.permissions_boundary_arn

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
