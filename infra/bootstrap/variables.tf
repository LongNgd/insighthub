variable "aws_region" {
  description = "AWS region where the Terraform state bucket is created."
  type        = string
  default     = "ap-southeast-1"
}

variable "aws_profile" {
  description = "Optional local AWS profile. Leave empty when credentials come from the environment or OIDC."
  type        = string
  default     = ""
}

variable "bucket_prefix" {
  description = "Globally unique bucket-name prefix; account ID and region are appended automatically."
  type        = string
  default     = "do2603-ndlong-tfstate"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,36}[a-z0-9]$", var.bucket_prefix))
    error_message = "bucket_prefix must contain 3-38 lowercase letters, digits, or hyphens and cannot start or end with a hyphen."
  }
}

variable "project" {
  description = "Required project tag."
  type        = string
  default     = "insighthub"
}

variable "environment" {
  description = "Required environment tag."
  type        = string
  default     = "production"
}

variable "owner" {
  description = "Required owner tag."
  type        = string
  default     = "Nguyen Dinh Long"
}

variable "cost_center" {
  description = "Required cost-center tag."
  type        = string
  default     = "do2603-lab"
}

