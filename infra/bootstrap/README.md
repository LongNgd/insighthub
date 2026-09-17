# Terraform state bootstrap

This independent Terraform root creates the S3 bucket required by the main
`infra/` backend. Its first apply intentionally uses local state because an S3
backend cannot create the bucket that it needs during initialization. After
creation, migrate the bootstrap state into a separate key in the same bucket.

Run this stack once before initializing the production root:

```bash
terraform -chdir=infra/bootstrap init -backend=false
terraform -chdir=infra/bootstrap plan -out=bootstrap.tfplan
terraform -chdir=infra/bootstrap apply bootstrap.tfplan

terraform -chdir=infra/bootstrap init -migrate-state -force-copy \
  -backend-config="bucket=do2603-ndlong-tfstate-154931139523-ap-southeast-1" \
  -backend-config="key=insighthub/bootstrap/terraform.tfstate" \
  -backend-config="region=ap-southeast-1"
```

Then read `bucket_name`, `backend_key`, and `backend_region` from
`terraform -chdir=infra/bootstrap output` and pass them to the main root's
`terraform init -backend-config=...` command.

The bucket has versioning, SSE-S3 encryption, public-access blocking,
bucket-owner-enforced ownership, an HTTPS-only bucket policy, and retention of
noncurrent state versions. `prevent_destroy` protects the bucket from an
accidental bootstrap destroy. Never commit the temporary local state produced
during first-time bootstrap.
