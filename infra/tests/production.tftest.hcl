mock_provider "aws" {}
mock_provider "kubernetes" {}
mock_provider "random" {}

override_data {
  target = data.aws_eks_cluster.this
  values = {
    endpoint = "https://eks.example.invalid"
    certificate_authority = [{
      data = "dGVzdC1jYQ=="
    }]
    identity = [{
      oidc = [{
        issuer = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE"
      }]
    }]
  }
}

override_data {
  target = data.aws_eks_cluster_auth.this
  values = {
    token = "mock-eks-token"
  }
}

override_data {
  target = data.aws_iam_openid_connect_provider.this
  values = {
    arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE"
    url = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE"
  }
}

override_data {
  target = module.insighthub_production.data.aws_region.current
  values = {
    region = "ap-southeast-1"
  }
}

# Mock providers synthesize arbitrary computed strings. IAM role/policy
# resources still validate that policy-document JSON is an object, so provide
# deterministic valid JSON for the three policy-document data sources.
override_data {
  target = module.insighthub_production.data.aws_iam_policy_document.assume_role
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

override_data {
  target = module.insighthub_production.data.aws_iam_policy_document.workload
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

override_data {
  target = module.insighthub_production.data.aws_iam_policy_document.rds_monitoring_assume_role
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

variables {
  vpc_id = "vpc-0123456789abcdef0"
  private_subnet_ids = [
    "subnet-0123456789abcdef0",
    "subnet-0123456789abcdef1",
  ]
  workload_security_group_ids = [
    "sg-0123456789abcdef0",
  ]
  owner       = "platform-team"
  cost_center = "do2603-lab"
}

run "production_dependencies_plan" {
  command = plan

  assert {
    condition     = module.insighthub_production.namespace == "insighthub"
    error_message = "The production namespace must be insighthub."
  }

  assert {
    condition     = module.insighthub_production.rds_port == 5432
    error_message = "RDS must expose PostgreSQL on port 5432."
  }

  assert {
    condition     = module.insighthub_production.redis_port == 6379
    error_message = "ElastiCache must expose Redis on port 6379."
  }

}
