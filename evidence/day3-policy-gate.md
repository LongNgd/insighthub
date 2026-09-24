# Day 3 policy gate — 2026-09-24

## Local static checks

| Check | Result |
| --- | --- |
| `terraform -chdir=infra fmt -check -recursive` | PASS |
| `terraform -chdir=infra init -backend=false -input=false` | PASS; pinned providers unchanged |
| `terraform -chdir=infra validate` | PASS |
| `(cd infra && tflint --recursive)` | PASS, no output |
| `checkov -d infra/ --framework terraform --compact --quiet` | PASS, exit 0; 164 passed, 0 failed, 0 skipped; see `day3-checkov.txt` |
| `bash scripts/test-terraform-policy.sh` | PASS; 25 policy checks on valid/invalid fixtures |
| `python -m unittest tests/test_redis_rotation.py` | PASS; 3 tests |
| `git diff --check` | PASS |

Five original Checkov findings were addressed: `CKV_AWS_38` and `CKV_AWS_39` by EKS private-only endpoint, `CKV_AWS_157` by RDS Multi-AZ, `CKV2_AWS_50` by Redis two-node Multi-AZ/failover, and `CKV2_AWS_57` by Secrets Manager rotation with a Lambda that creates, applies, verifies, and promotes a token. No checks were skipped or suppressed. New Lambda/IAM/logging findings found during implementation were also fixed before recording the zero-finding report.

## Still pending

Conftest has **not** run on an AWS-backed Terraform plan. The WSL environment has no `aws` CLI and no sandbox account, region, VPC/subnet IDs, state backend or signed Lambda artifact inputs. The owner confirmed there is no sandbox yet and requested stopping at the static gate. No `terraform plan`, `apply`, AWS resource creation, rotation invocation, Infracost estimate or runtime smoke was performed. The full policy gate is **PENDING**, despite local static checks passing.

Before a real plan: verify AWS identity, private network access to EKS, existing private subnets in two AZs, S3 backend, AWS Signer-signed Lambda ZIP and profile version ARN; estimate the added RDS standby, Redis replica, interface endpoints, Lambda/SQS/Signer/X-Ray costs. Run `terraform plan` with `manage_namespace=false`, then `bash scripts/test-terraform-policy-plan.sh /absolute/path/to/day3.tfplan`; retain only redacted output and exit status. After a separately approved apply, test rotation end-to-end, refresh the Kubernetes runtime Secret and workloads, and confirm a subsequent plan does not restore the old token.
