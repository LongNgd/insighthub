# InsightHub Day 3 infrastructure

`infra/` is the production root module. It calls the reusable module at
`modules/insighthub-production/`; there is deliberately no `examples/` tree.

The configuration targets the existing EKS cluster
`insighthub-prod-cluster`. It creates the `insighthub` namespace and private
RDS/ElastiCache dependencies. It never creates an EKS cluster.

## Prerequisites

- Terraform 1.11 or newer.
- AWS identity scoped to the lab account/region.
- Existing EKS cluster, IAM OIDC provider, VPC, and private subnets.
- Explicit EKS workload security group IDs.
- Existing S3 state bucket with versioning and encryption enabled.
- Network access to the EKS Kubernetes API for namespace/ServiceAccount plans.

## Initialize

Backend values are intentionally partial and environment-specific:

```bash
terraform -chdir=infra init \
  -backend-config="bucket=<state-bucket>" \
  -backend-config="key=insighthub/production/terraform.tfstate" \
  -backend-config="region=ap-southeast-1"
```

For local validation without AWS state access:

```bash
terraform -chdir=infra init -backend=false
terraform -chdir=infra validate
terraform -chdir=infra fmt -check -recursive
tflint --chdir=infra --recursive --config="$PWD/infra/.tflint.hcl"
checkov -d infra/
```

## Policy gate

Generate a machine-readable Terraform plan and evaluate the project-specific
Conftest policies:

```bash
terraform -chdir=infra plan -out=tfplan
terraform -chdir=infra show -json tfplan > tfplan.json
conftest test --policy infra/policies tfplan.json
python3 -m pytest tests/milestones/day3/test_terraform_policies.py -v
```

The policies reject missing ownership tags, unencrypted or public data
services, unrestricted security-group ingress, unsafe IAM, creation of a new
EKS cluster, and RDS/Redis sizes outside the approved lab profile. Never commit
the binary or JSON plan because it can contain sensitive values.

Copy `terraform.tfvars.example` outside version control or pass variables via
CI. Never commit real account IDs, subnet IDs, credentials, tokens, or plan
files containing sensitive values.

## Plan and review

```bash
terraform -chdir=infra plan -out=lab.tfplan
terraform -chdir=infra show lab.tfplan
```

Review the account, region, resource IDs, tags, cost, and all destroy actions.
Do not apply a plan containing unexpected replacement or deletion.

## pgvector

RDS PostgreSQL supports pgvector, but AWS does not expose extension creation as
an RDS provisioning property. The module creates a ConfigMap containing:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

The Helm/database migration job must execute this statement using credentials
retrieved from the RDS-managed Secrets Manager secret before the API and worker
start. The complete application schema remains in `db/init.sql`.

## Lab cleanup

Use a reviewed destroy plan immediately after the lab. Then check for retained
RDS snapshots/backups, ElastiCache snapshots, ENIs, KMS keys pending deletion,
Secrets Manager recovery-window entries, and other resources recorded in the
lab manifest. Empty Terraform state alone is not proof that AWS is clean.
