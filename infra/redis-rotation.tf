# The rotation function needs private access to Redis and to both AWS APIs.
# Interface endpoints avoid relying on an existing NAT gateway.
resource "aws_security_group" "rotation" {
  name        = "${local.name}-rotation"
  description = "Outbound access for the Redis rotation Lambda"
  vpc_id      = data.aws_vpc.lab.id
}

resource "aws_security_group" "rotation_endpoints" {
  name        = "${local.name}-rotation-endpoints"
  description = "Private AWS API endpoints for Redis rotation"
  vpc_id      = data.aws_vpc.lab.id
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_rotation" {
  description                  = "Redis AUTH verification from rotation Lambda"
  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = aws_security_group.rotation.id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "rotation_to_redis" {
  description                  = "Redis AUTH verification"
  security_group_id            = aws_security_group.rotation.id
  referenced_security_group_id = aws_security_group.redis.id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_from_rotation" {
  description                  = "AWS API calls from rotation Lambda"
  security_group_id            = aws_security_group.rotation_endpoints.id
  referenced_security_group_id = aws_security_group.rotation.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "rotation_to_endpoints" {
  description                  = "Private AWS API calls"
  security_group_id            = aws_security_group.rotation.id
  referenced_security_group_id = aws_security_group.rotation_endpoints.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_vpc_endpoint" "rotation_api" {
  for_each = toset(["secretsmanager", "elasticache"])

  vpc_id              = data.aws_vpc.lab.id
  service_name        = "com.amazonaws.${var.aws_region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.rotation_endpoints.id]
  private_dns_enabled = true
}

resource "aws_iam_role" "redis_rotation" {
  name = "${local.name}-redis-rotation"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "redis_rotation_vpc" {
  role       = aws_iam_role.redis_rotation.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy_attachment" "redis_rotation_xray" {
  role       = aws_iam_role.redis_rotation.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

resource "aws_iam_role_policy" "redis_rotation" {
  name = "${local.name}-redis-rotation"
  role = aws_iam_role.redis_rotation.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:DescribeSecret",
          "secretsmanager:GetSecretValue",
          "secretsmanager:PutSecretValue",
          "secretsmanager:UpdateSecretVersionStage",
        ]
        Resource = aws_secretsmanager_secret.redis.arn
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetRandomPassword"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["elasticache:DescribeReplicationGroups", "elasticache:ModifyReplicationGroup"]
        Resource = aws_elasticache_replication_group.this.arn
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
        Resource = aws_kms_key.lab.arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.redis_rotation.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.redis_rotation_failures.arn
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "redis_rotation" {
  name              = "/aws/lambda/${local.name}-redis-rotation"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.lab.arn
}

resource "aws_sqs_queue" "redis_rotation_failures" {
  name                      = "${local.name}-rotation-failures"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_lambda_code_signing_config" "redis_rotation" {
  allowed_publishers {
    signing_profile_version_arns = [var.rotation_signing_profile_version_arn]
  }
  policies {
    untrusted_artifact_on_deployment = "Enforce"
  }
}

resource "aws_lambda_function" "redis_rotation" {
  function_name                  = "${local.name}-redis-rotation"
  role                           = aws_iam_role.redis_rotation.arn
  runtime                        = "python3.12"
  handler                        = "handler.lambda_handler"
  s3_bucket                      = var.rotation_signed_s3_bucket
  s3_key                         = var.rotation_signed_s3_key
  s3_object_version              = var.rotation_signed_s3_object_version
  code_signing_config_arn        = aws_lambda_code_signing_config.redis_rotation.arn
  timeout                        = 180
  reserved_concurrent_executions = 1
  kms_key_arn                    = aws_kms_key.lab.arn

  dead_letter_config {
    target_arn = aws_sqs_queue.redis_rotation_failures.arn
  }

  tracing_config {
    mode = "Active"
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.rotation.id]
  }

  environment {
    variables = {
      REDIS_REPLICATION_GROUP = aws_elasticache_replication_group.this.id
      REDIS_HOST              = aws_elasticache_replication_group.this.primary_endpoint_address
      SECRET_ARN              = aws_secretsmanager_secret.redis.arn
    }
  }

  depends_on = [
    aws_iam_role_policy.redis_rotation,
    aws_iam_role_policy_attachment.redis_rotation_vpc,
    aws_iam_role_policy_attachment.redis_rotation_xray,
    aws_cloudwatch_log_group.redis_rotation,
    aws_vpc_endpoint.rotation_api,
  ]
}

resource "aws_lambda_permission" "redis_rotation" {
  statement_id   = "AllowSecretsManagerRotation"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.redis_rotation.function_name
  principal      = "secretsmanager.amazonaws.com"
  source_arn     = aws_secretsmanager_secret.redis.arn
  source_account = var.aws_account_id
}

resource "aws_secretsmanager_secret_rotation" "redis" {
  secret_id           = aws_secretsmanager_secret.redis.id
  rotation_lambda_arn = aws_lambda_function.redis_rotation.arn
  rotate_immediately  = false

  rotation_rules {
    automatically_after_days = 30
  }

  depends_on = [
    aws_lambda_permission.redis_rotation,
    aws_secretsmanager_secret_version.redis,
  ]
}
