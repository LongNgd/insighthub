output "bucket_name" {
  description = "S3 bucket used by the InsightHub production Terraform backend."
  value       = aws_s3_bucket.terraform_state.id
}

output "backend_key" {
  description = "Recommended state key for the production root module."
  value       = "insighthub/production/terraform.tfstate"
}

output "backend_region" {
  description = "Region containing the Terraform state bucket."
  value       = data.aws_region.current.region
}

