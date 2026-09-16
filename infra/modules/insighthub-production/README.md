# InsightHub production dependencies module

This module attaches InsightHub to an **existing** EKS cluster. It does not
create or modify an EKS cluster or node group.

## Resources

- Kubernetes namespace and IRSA-enabled ServiceAccount.
- Private, encrypted RDS PostgreSQL 16 (`db.t3.small`, GP3 20 GiB, single-AZ).
- Private, encrypted ElastiCache Redis OSS 7.1 (`cache.t3.micro`, one node).
- RDS-managed master password and a Redis connection secret in Secrets Manager.
- Narrow security-group ingress from explicitly supplied EKS workload security groups.
- Optional dedicated rotating KMS key.
- Idempotent pgvector bootstrap SQL in a namespaced ConfigMap.

The deployment migration job must execute `001-enable-pgvector.sql` before the
API/worker starts. Terraform intentionally does not connect directly to the
private database or run `local-exec`.

## Required inputs

| Input | Description |
|---|---|
| `cluster_name` | Existing EKS cluster name. |
| `cluster_oidc_issuer_url` | Cluster OIDC issuer URL. |
| `cluster_oidc_provider_arn` | Existing IAM OIDC provider ARN. |
| `vpc_id` | VPC shared with EKS. |
| `private_subnet_ids` | At least two private subnets. |
| `workload_security_group_ids` | EKS workload SGs allowed to connect. |
| `tags` | `project`, `environment`, `owner`, `cost_center`. |

See `variables.tf` for documented optional inputs and lab-sized defaults.

## Security notes

- No CIDR ingress is created; access is SG-to-SG only.
- RDS is not publicly accessible.
- RDS, Redis, Secrets Manager, and Performance Insights use KMS encryption.
- Redis requires TLS and an auth token.
- The IRSA trust policy is bound to one namespace and ServiceAccount.
- The workload role can read only the two module-owned secrets.
- The Redis token must be supplied to the ElastiCache API and is therefore
  sensitive Terraform state. Use an encrypted S3 backend with tightly scoped
  access and native lockfiles.
