data "aws_iam_policy_document" "assume_role" {
  statement {
    sid     = "AllowInsightHubServiceAccount"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.cluster_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_hostpath}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_hostpath}:sub"
      values   = ["system:serviceaccount:${var.namespace}:${var.service_account_name}"]
    }
  }
}

resource "aws_iam_role" "workload" {
  name                 = "${local.name_prefix}-workload"
  description          = "IRSA role for InsightHub pods in ${var.namespace}"
  assume_role_policy   = data.aws_iam_policy_document.assume_role.json
  permissions_boundary = var.permissions_boundary_arn

  tags = local.common_tags
}

data "aws_iam_policy_document" "workload" {
  statement {
    sid    = "ReadOnlyInsightHubSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      aws_db_instance.this.master_user_secret[0].secret_arn,
      aws_secretsmanager_secret.redis.arn,
    ]
  }

  statement {
    sid       = "DecryptInsightHubSecrets"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [local.kms_key_arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${data.aws_region.current.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "workload" {
  name   = "read-insighthub-secrets"
  role   = aws_iam_role.workload.id
  policy = data.aws_iam_policy_document.workload.json
}
