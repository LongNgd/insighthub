resource "aws_kms_key" "this" {
  # checkov:skip=CKV2_AWS_64:AWS applies the default account key policy; an external key with an organization-managed policy can be supplied via kms_key_arn.
  count = var.kms_key_arn == null ? 1 : 0

  description             = "InsightHub ${var.tags.environment} data encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  key_usage               = "ENCRYPT_DECRYPT"
  multi_region            = false

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-data"
  })
}

resource "aws_kms_alias" "this" {
  count = var.kms_key_arn == null ? 1 : 0

  name          = "alias/${local.name_prefix}-data"
  target_key_id = aws_kms_key.this[0].key_id
}
