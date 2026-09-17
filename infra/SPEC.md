# InsightHub Production Infrastructure Specification

## 1. Document control

| Field | Value |
|---|---|
| Project | InsightHub |
| Scope | Day 3 — AWS infrastructure, Kubernetes deployment, and CI/CD |
| Version | 0.1.0 |
| Status | Draft |
| Owner | Nguyen Dinh Long |
| AWS region | `ap-southeast-1` unless the approved lab manifest says otherwise |
| Environment | `production` intent with time-boxed lab sizing |
| Lab expiry | TBD in `lab-manifest.json` before any AWS apply |

This specification is the source contract for Terraform, Helm, policies, and
the GitHub Actions pipeline. Implementation changes that alter architecture,
security, cost, or acceptance criteria require this document to be reviewed.

## 2. Objective

Create the AWS foundation and deploy InsightHub with:

- A dedicated VPC across two Availability Zones.
- An EKS cluster named `insighthub-prod-cluster` with private managed nodes.
- Kubernetes namespace `insighthub-production` (`insighthub-<env>` contract).
- Web, API, and ingestion-worker workloads.
- Private RDS PostgreSQL 16 with the `vector` extension.
- Private ElastiCache Redis OSS 7.
- IRSA for pod access to AWS Secrets Manager.
- HTTPS ingress and end-to-end upload, ingestion, and chat smoke tests.
- Reproducible Terraform/Helm delivery through a policy-gated GitHub pipeline.

## 3. Scope

### 3.1 In scope

- Reusable network, EKS, application-dependency modules, and production root configuration.
- S3 Terraform backend with native lockfile support.
- RDS, ElastiCache, subnet groups, security groups, KMS, and Secrets Manager.
- Kubernetes namespace, ServiceAccount, IRSA role, and database bootstrap data.
- Helm deployment for web, API, ingestion-worker, migration, services, HPA,
  ConfigMaps, secret integration, and HTTPS ingress.
- TFLint, Checkov, Conftest, tests, Infracost, CI/CD, smoke evidence, and teardown.

### 3.2 Out of scope

- Connecting this lab VPC to unrelated VPCs or on-premises networks.
- Managing organization-wide DNS, IAM Identity Center, or shared networking.
- Creating IAM users or long-lived AWS access keys.
- Running PostgreSQL or Redis as StatefulSets in EKS.
- Changing the InsightHub HTTP contract or embedding identity.
- Treating lab sizing as a recommended long-lived production topology.

## 4. Preconditions and external dependencies

The following must exist before a real plan or apply:

| Dependency | Required state |
|---|---|
| AWS account | Enough quota and permission to create VPC, NAT, EKS, EC2, IAM, KMS, RDS, Redis, and logs |
| EKS API access | Restricted operator/CI IPv4 CIDRs; never `0.0.0.0/0` |
| Availability Zones | At least two standard AZs in the selected region |
| Terraform state bucket | Versioned, encrypted, access restricted |
| Container registry | Immutable image tags or digests |
| DNS/TLS | Approved DNS name and certificate |
| GitHub environment | Manual approval enabled for production |
| GitHub OIDC role | Trust bound to repository and environment |

Terraform must stop rather than invent IDs when any required dependency is
unknown. The operator must verify account, region, workspace, and identity
before plan, apply, and destroy.

## 5. Target architecture

```text
Internet
  -> Internet Gateway -> public subnets -> NAT Gateway
  -> restricted EKS public API endpoint
  -> HTTPS Ingress / AWS load balancer
      -> web Service -> web Deployment
      -> api Service -> api Deployment
                         |-> private RDS PostgreSQL 16 + pgvector
                         `-> private ElastiCache Redis 7
      ingestion-worker Deployment
                         |-> private ElastiCache Redis 7
                         `-> private RDS PostgreSQL 16 + pgvector

Dedicated VPC
  - two public subnets
  - two private subnets for EKS nodes, RDS, and Redis

EKS cluster: insighthub-prod-cluster
EKS namespace: insighthub-production
  - ServiceAccount: insighthub (IRSA)
  - migration Job runs before API and worker rollout

AWS supporting services
  - Secrets Manager: RDS-managed master secret and Redis connection secret
  - KMS: encryption for RDS, Redis, secrets, and Performance Insights
  - S3: encrypted/versioned Terraform state with native lockfile
```

RDS and Redis are managed services and must not be counted as Kubernetes pods.

## 6. Environment profile

The code expresses production security intent but uses disposable lab capacity.

| Decision | Lab setting | Long-lived production target |
|---|---|---|
| RDS class | `db.t3.small` | Re-evaluate from measured workload |
| RDS availability | Single-AZ | Multi-AZ |
| RDS storage | GP3, 20 GiB | Size and autoscaling from measurements |
| RDS deletion protection | Disabled for teardown | Enabled |
| RDS backup | 1 day, no final snapshot by default | At least 7 days and approved retention |
| Redis class | `cache.t3.micro` | Re-evaluate from queue/cache metrics |
| Redis availability | One node, no failover | Replica and automatic failover |
| Redis secret rotation | Destroyed with lab | Coordinated automatic rotation |
| Environment lifetime | One lab run | Continuous |

Lab exceptions must not be promoted to a persistent production environment
without an explicit review and a new approved plan.

## 7. Terraform contract

### 7.1 Layout

```text
infra/
  backend.tf                         # production root backend
  providers.tf                       # AWS and Kubernetes providers
  main.tf                            # calls reusable module
  variables.tf / outputs.tf
  terraform.tfvars.example
  modules/network/                   # reusable VPC and subnet module
  modules/eks/                       # reusable EKS and node module
  modules/insighthub-production/     # reusable application dependencies
```

### 7.2 Provider and runtime constraints

- Terraform: `>= 1.11.0, < 2.0.0`.
- AWS provider: `~> 6.64`.
- Kubernetes provider: `~> 3.2`.
- Random provider: `~> 3.9`.
- TLS provider: `~> 4.1`.
- Provider selections are committed in `.terraform.lock.hcl`.

### 7.3 Required inputs

| Input | Constraint |
|---|---|
| `eks_cluster_name` | Must be `insighthub-prod-cluster` in the production root |
| `vpc_cidr` | Dedicated non-overlapping VPC CIDR |
| `eks_public_access_cidrs` | Restricted operator/CI CIDRs; `0.0.0.0/0` forbidden |
| `kubernetes_version` | Supported EKS Kubernetes version |
| `eks_node_instance_types` | Approved managed-node instance types |
| `owner` | Non-empty required tag |
| `cost_center` | Non-empty required tag |

### 7.4 Invariants

- No IAM user or access key resource.
- No plaintext secret input, output, log, committed tfvars, or Helm value.
- No ingress or egress rule using `0.0.0.0/0`.
- No public RDS or Redis endpoint.
- All taggable resources include `project`, `environment`, `owner`,
  `cost_center`, and `managed_by`.
- Sensitive plan/state files are not committed.

## 8. State management

The root uses an S3 backend with `encrypt = true` and `use_lockfile = true`.
Bucket, key, and region are supplied during `terraform init` because backend
configuration cannot use Terraform variables.

The state bucket must have:

- Versioning and server-side encryption.
- Least-privilege access for CI and approved operators.
- Public access blocked.
- Logging/audit appropriate to the lab account.
- A unique production state key.

The Redis auth token is passed to the ElastiCache API and is therefore present
as sensitive Terraform state. State access is equivalent to secret access.
`.tfstate`, `.tfvars`, `.tfplan`, and plan JSON files must not be committed.

## 9. Data services

### 9.1 RDS PostgreSQL

- Engine: PostgreSQL `16.15` by default; only PostgreSQL 16 minors are valid.
- Class: `db.t3.small`.
- Storage: GP3, 20 GiB, encrypted with the selected customer-managed KMS key.
- Availability: single-AZ for the lab.
- Network: private subnets, `publicly_accessible = false`.
- Security group: TCP 5432 only from supplied workload security groups.
- TLS forced through the PostgreSQL parameter group.
- RDS-managed master password stored in Secrets Manager.
- IAM database authentication and encrypted Performance Insights enabled.
- PostgreSQL and upgrade logs exported to CloudWatch.
- Enhanced monitoring enabled.

### 9.2 ElastiCache Redis

- Engine: Redis OSS `7.1`.
- Node: one `cache.t3.micro` node.
- Network: private subnets only.
- Security group: TCP 6379 only from supplied workload security groups.
- Encryption at rest with KMS.
- Encryption in transit required.
- Random auth token stored with endpoint metadata in Secrets Manager.
- One-day snapshot retention for the lab.

## 10. Database and pgvector lifecycle

AWS does not expose PostgreSQL extension creation as an RDS provisioning
property. Terraform creates an `insighthub-database-bootstrap` ConfigMap with:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

The Helm deployment must provide an idempotent migration Job that:

1. Uses the `insighthub` IRSA ServiceAccount.
2. Retrieves the RDS-managed credential from Secrets Manager without logging it.
3. Connects to the private RDS endpoint using TLS.
4. Runs the pgvector statement.
5. Applies `infra/db/init.sql` or a versioned equivalent.
6. Exits non-zero on any failure.
7. Completes before API and ingestion-worker rollout.

Terraform must not use `local-exec` to connect to the private database. A
failed migration blocks rollout; it must not fall back to another database.

## 11. Secrets and IAM

### 11.1 Workload IRSA

The trust policy is restricted to:

```text
system:serviceaccount:insighthub-production:insighthub
```

It also validates the `sts.amazonaws.com` audience. The workload role may only:

- Describe/read the RDS master secret.
- Describe/read the Redis secret.
- Decrypt the selected KMS key through Secrets Manager.

It must not grant secret write, IAM mutation, wildcard service actions, or
access to unrelated secret ARNs.

### 11.2 GitHub OIDC

The CI role is separate from workload IRSA. Its trust must bind the exact
GitHub organization/repository and approved ref or GitHub Environment. It must
not use broad subject wildcards or long-lived AWS keys.

### 11.3 Secret delivery to pods

The deployment uses the AWS Secrets Store CSI Driver with the AWS provider to
mount secrets from AWS Secrets Manager into authorized pods through IRSA.
Kubernetes Secret objects, if materialized, must be namespace-scoped, encrypted
at rest by the cluster, and must never be committed or printed by CI.

## 12. Network security

- EKS nodes, RDS, and Redis use only the module-created private subnets.
- The EKS API always has private access; optional public access is CIDR-restricted.
- Access is security-group-to-security-group, not CIDR-wide.
- RDS permits only TCP 5432 from approved workload SGs.
- Redis permits only TCP 6379 from approved workload SGs.
- Data-service security groups have no unrestricted egress rule.
- Redis clients must use TLS.
- PostgreSQL clients must require SSL.
- Public EKS API access is disabled by default and, when enabled, accepts only
  explicitly configured operator/CI CIDRs.

## 13. Helm deployment contract

The chart must define:

- Deployments for `web`, `api`, and `ingestion-worker`.
- Services for `web` and `api`.
- The existing Terraform-managed `insighthub` ServiceAccount or an explicit
  no-create reference to it.
- ConfigMaps only for non-sensitive settings.
- Approved Secrets Manager integration.
- Migration Job for pgvector and schema initialization.
- Readiness/liveness probes and resource requests/limits.
- HPA for the API.
- Rolling update strategy and immutable image references.
- HTTPS ingress and an approved TLS certificate.
- Environment-specific values without duplicated secrets.

The application contract remains:

- `POST /documents` returns 202.
- Worker processes the queued document to `ready` or `failed`.
- `POST /chat` returns an answer and sources for ready documents.

## 14. CI/CD contract

Required pipeline order:

```text
fmt + lint + security-scan + policy-check
  -> application tests
  -> image build and scan
  -> Terraform plan
  -> Infracost
  -> manual production approval
  -> apply the reviewed plan
  -> Helm deploy and migration
  -> smoke test
```

Rules:

- Pull requests never apply infrastructure.
- Production apply uses a GitHub Environment approval gate.
- AWS authentication uses OIDC with `id-token: write`; default permissions are
  `contents: read`.
- Third-party actions are pinned to immutable commit SHAs.
- The applied plan is the same reviewed plan artifact.
- Source and deployment artifacts are bound by SHA-256.
- CI uploads `verification-source/source-manifest.json` for the Day 3 verifier.
- Failure in scan, policy, migration, or smoke stops the pipeline.

## 15. Three-layer defense and policy gates

### 15.1 AI generation

AI-generated changes must cite this specification and existing repository
constraints. Generated code is never applied automatically from an unreviewed
conversation or branch.

### 15.2 Human review

The reviewer checks account, region, resource identities, IAM scope, network,
encryption, cost, replacement/destroy actions, sensitive outputs, and teardown.

### 15.3 Automated gates

- `terraform fmt -check -recursive`: no differences.
- `terraform validate`: success.
- `tflint --recursive`: zero warnings.
- `checkov -d infra/`: no failed HIGH/CRITICAL checks.
- Conftest: valid plan allowed and unsafe plan denied.

Conftest must reject:

- Missing required tags.
- Unencrypted RDS/Redis/storage.
- Public RDS/Redis or public CIDR security-group rules.
- IAM users, access keys, wildcard IAM actions/resources where restrictable.
- EKS clusters without secret encryption, control-plane logging, or private API access.
- RDS/Redis sizes outside the approved lab profile without explicit approval.

Every policy exception requires policy ID, rationale, owner, expiry, and
production remediation. Current lab exceptions are:

| Policy | Rationale | Expiry/remediation |
|---|---|---|
| `CKV_AWS_157` | Single-AZ RDS required by lab cost constraint | Enable Multi-AZ before persistent production |
| `CKV_AWS_293` | Deletion protection defaults off for teardown | Enable for persistent production |
| `CKV2_AWS_50` | Single Redis node required by lab cost constraint | Add replica/failover before persistent production |
| `CKV2_AWS_57` | Lab token is destroyed after the run | Implement coordinated Redis/client rotation |
| `CKV2_AWS_64` | Lab may use default account key policy | Supply organization-managed KMS key/policy |
| `CKV_AWS_158` | VPC Flow Logs use CloudWatch service-side encryption in the lab | Use an organization-managed logging KMS key for persistent production |

## 16. Acceptance criteria

### 16.1 Static and policy

| ID | Requirement | Command/evidence | Expected |
|---|---|---|---|
| AC-S1 | Terraform formatted | `terraform -chdir=infra fmt -check -recursive` | Exit 0, no diff |
| AC-S2 | Terraform valid | `terraform -chdir=infra validate` | Success |
| AC-S3 | Module plan contract | `terraform -chdir=infra test` | All tests pass |
| AC-S4 | TFLint clean | `tflint --chdir=infra --recursive` | 0 warnings/errors |
| AC-S5 | Checkov clean | `checkov -d infra/` | No failed HIGH/CRITICAL |
| AC-S6 | Conftest valid fixture | `pytest tests/milestones/day3` | `test_policy_allows_valid` passes |
| AC-S7 | Conftest unsafe fixture | `pytest tests/milestones/day3` | `test_policy_denies_unsafe` passes |

### 16.2 AWS plan and resources

| ID | Requirement | Command/evidence | Expected |
|---|---|---|---|
| AC-A1 | Correct AWS identity | `aws sts get-caller-identity` | Approved lab account/role |
| AC-A2 | S3 state and locking | `terraform init` logs/backend config | Success with `use_lockfile` |
| AC-A3 | Reviewed deterministic plan | Saved plan and repeated no-change plan | No unexpected destroy/drift |
| AC-A4 | Dedicated EKS foundation | Plan/resource inventory | VPC, EKS cluster, and private node group created |
| AC-A5 | Private encrypted RDS 16 | Plan and AWS describe output | PostgreSQL 16, encrypted, not public, single-AZ |
| AC-A6 | Private encrypted Redis 7 | Plan and AWS describe output | Redis 7, at-rest/transit encryption, one node |
| AC-A7 | Required tags | AWS tag inventory | All five tags present |
| AC-A8 | Least-privilege IRSA | IAM trust/policy evidence | One namespace/SA and two secret ARNs only |
| AC-A9 | Cost estimate | Infracost report | Region/time/add-ons included and within budget |

### 16.3 Kubernetes

| ID | Requirement | Command/evidence | Expected |
|---|---|---|---|
| AC-K1 | Namespace | `kubectl get ns insighthub-production` | Active |
| AC-K2 | IRSA ServiceAccount | `kubectl describe sa insighthub -n insighthub-production` | Correct role annotation |
| AC-K3 | Migration | `kubectl get job -n insighthub-production` and logs | Complete, no secret output |
| AC-K4 | pgvector | SQL extension query | `vector` installed |
| AC-K5 | Workloads | `kubectl get pods -n insighthub-production` | Web/API/worker Ready |
| AC-K6 | HTTPS health | `curl https://<approved-host>/healthz` | HTTP 200 |

### 16.4 Application smoke

| ID | Requirement | Command/evidence | Expected |
|---|---|---|---|
| AC-P1 | Async upload | `POST /documents` | HTTP 202 in under 1 second |
| AC-P2 | Background ingestion | Poll `GET /documents` | Matching document `ready` within 30 seconds |
| AC-P3 | Chat | `POST /chat` | HTTP 200, non-empty answer and sources |

## 17. Evidence and provenance

Required artifacts:

- Approved `infra/SPEC.md` and source commit.
- Terraform fmt/validate/TFLint/Checkov/Conftest reports.
- Reviewed plan summary with sensitive values removed.
- Infracost report with pricing source/date.
- GitHub Actions run URL and approval evidence.
- `verification-source/source-manifest.json` with source/artifact SHA-256.
- Kubernetes namespace, ServiceAccount, job, pod, ingress, and smoke evidence.
- AWS encryption/network/tag/IAM evidence without credentials.
- `ai-prompts/day3.md` with at least three prompts and accept/reject rationale.
- `evidence/day3.json`, deployment artifact, and CI binding.
- Before/after inventory and teardown report.

Fixture or mock plan evidence proves only the checked contract. It does not
prove AWS deployment, GitHub provenance, or live application health.

## 18. Rollback and teardown

### 18.1 Rollback

- Do not apply a plan with unexpected destroy or replacement.
- Failed Helm rollout uses the previously verified release revision.
- Failed migration blocks API/worker deployment and is investigated; it is not
  bypassed or replaced with an alternate database.
- Do not force-unlock state until the lock owner/process is verified stale.
- Application failure does not authorize unreviewed database deletion.

### 18.2 Teardown order

1. Capture final smoke, inventory, elapsed time, and evidence.
2. Remove ingress/services that provision external load balancers.
3. Remove application workloads and migration resources.
4. Generate and review an exact Terraform destroy plan.
5. Apply that reviewed destroy plan.
6. Verify state and query all used regions for orphaned resources.
7. Check RDS backups/snapshots, Redis snapshots, ENIs, SGs, KMS pending
   deletion, Secrets Manager recovery entries, ECR, load balancers, and logs.
8. Record actual/estimated cost and cleanup timestamp.

Empty Terraform state alone is not proof of cleanup. Any retained resource must
have an owner, reason, expiry, and approved cost.
