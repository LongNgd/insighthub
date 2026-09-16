terraform {
  backend "s3" {
    encrypt      = true
    use_lockfile = true
  }
}

# Supply bucket, key, and region at init time. Backend arguments cannot use
# Terraform input variables. See README.md for the exact command.
