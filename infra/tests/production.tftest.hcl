mock_provider "aws" {}
mock_provider "kubernetes" {}
mock_provider "random" {}
mock_provider "tls" {}

override_data {
  target = data.aws_availability_zones.available
  values = {
    names = ["ap-southeast-1a", "ap-southeast-1b", "ap-southeast-1c"]
  }
}

override_data {
  target = data.aws_eks_cluster_auth.this
  values = {
    token = "test"
  }
}

override_resource {
  target = module.eks.aws_eks_cluster.this
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
  target = module.eks.data.tls_certificate.oidc
  values = {
    certificates = [{
      sha1_fingerprint = "0123456789abcdef0123456789abcdef01234567"
    }]
  }
}

# Mock providers synthesize arbitrary computed strings. IAM role/policy
# resources still validate that policy-document JSON is an object, so provide
# deterministic valid JSON for all policy-document data sources.
override_data {
  target = module.network.data.aws_iam_policy_document.flow_assume_role
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

override_data {
  target = module.network.data.aws_iam_policy_document.flow
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

override_data {
  target = module.eks.data.aws_iam_policy_document.cluster_assume_role
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

override_data {
  target = module.eks.data.aws_iam_policy_document.node_assume_role
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

override_data {
  target = module.insighthub_production.data.aws_region.current
  values = {
    region = "ap-southeast-1"
  }
}

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
  owner                   = "platform-team"
  cost_center             = "do2603-lab"
  eks_public_access_cidrs = ["198.51.100.10/32"]
}

run "production_stack_plan" {
  command = plan

  assert {
    condition     = module.insighthub_production.namespace == "insighthub-production"
    error_message = "The production namespace must include the environment suffix."
  }

  assert {
    condition     = length(module.network.private_subnet_ids) == 2
    error_message = "The network must provide two private subnets."
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
