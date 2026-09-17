# InsightHub Day 3 infrastructure

`infra/` is the production root module. It composes reusable network, EKS, and
InsightHub dependency modules; there is deliberately no `examples/` tree.

The configuration creates a dedicated VPC, EKS cluster
`insighthub-prod-cluster`, private managed nodes, the
`insighthub-production` namespace, and private RDS/ElastiCache dependencies.
The VPC spans two Availability Zones with public subnets for one lab-sized NAT
Gateway and private subnets for EKS nodes, RDS, and Redis.

## Prerequisites

- Terraform 1.11 or newer.
- AWS identity scoped to the lab account/region.
- AWS permissions and service quotas for VPC, NAT Gateway, EKS, EC2, IAM, KMS,
  RDS, ElastiCache, Secrets Manager, and CloudWatch Logs.
- A restricted operator/CI egress CIDR for EKS API access. Keep
  `eks_public_access_cidrs` empty only when Terraform runs from inside the VPC.
- Permission to run the one-time `infra/bootstrap/` state-bucket stack.
- Network access to the EKS Kubernetes API for namespace/ServiceAccount plans.

## Bootstrap the state bucket

The backend bucket must exist before the production root can initialize. Create
it once with the independent local-state bootstrap stack:

```bash
terraform -chdir=infra/bootstrap init -backend=false
terraform -chdir=infra/bootstrap plan -out=bootstrap.tfplan
terraform -chdir=infra/bootstrap apply bootstrap.tfplan

terraform -chdir=infra/bootstrap init -migrate-state -force-copy \
  -backend-config="bucket=do2603-ndlong-tfstate-154931139523-ap-southeast-1" \
  -backend-config="key=insighthub/bootstrap/terraform.tfstate" \
  -backend-config="region=ap-southeast-1"
```

Do not commit the temporary local state or saved plan. The state bucket is
protected from Terraform destroy and is intentionally not part of the reusable
module. Bootstrap and production use separate state keys.

## Initialize the production root

Backend values are intentionally partial and environment-specific:

```bash
terraform -chdir=infra init \
  -backend-config="bucket=<bootstrap-bucket-output>" \
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
services, unrestricted security-group ingress, unsafe IAM, unsafe EKS API or
secret settings, and RDS/Redis sizes outside the approved lab profile. Never
commit the binary or JSON plan because it can contain sensitive values.

Copy `terraform.tfvars.example` outside version control or pass variables via
CI. Never commit credentials, tokens, or plan files containing sensitive
values. Replace the documentation-only EKS API CIDR before planning.

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

The Helm migration Job executes this statement and the complete schema copied
from `infra/db/init.sql`, using credentials retrieved from the RDS-managed
Secrets Manager secret before the API and worker start. The namespace-scoped
chart is in `infra/helm/insighthub`; its README documents validation and deploy
commands. The cluster-wide Secrets Store CSI Driver, AWS provider, AWS Load
Balancer Controller, and Metrics Server remain separately managed add-ons.

## Lab cleanup

Use a reviewed destroy plan immediately after the lab. Then check for retained
RDS snapshots/backups, ElastiCache snapshots, ENIs, KMS keys pending deletion,
Secrets Manager recovery-window entries, and other resources recorded in the
lab manifest. Empty Terraform state alone is not proof that AWS is clean.
