terraform {
  backend "s3" {
    encrypt      = true
    use_lockfile = true
  }
}

# Create the bucket first with infra/bootstrap, then supply its bucket, key,
# and region outputs at init time. Backend arguments cannot use Terraform input
# variables. See README.md for the exact two-phase commands.
