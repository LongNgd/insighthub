variable "aws_region" {
  description = "AWS region containing the existing EKS cluster and private data services."
  type        = string
  default     = "ap-southeast-1"
}

variable "aws_profile" {
  description = "Optional local AWS profile. Leave empty in GitHub Actions/OIDC."
  type        = string
  default     = ""
}

variable "eks_cluster_name" {
  description = "Name of the existing EKS cluster. This configuration never creates a cluster."
  type        = string
  default     = "insighthub-prod-cluster"

  validation {
    condition     = var.eks_cluster_name == "insighthub-prod-cluster"
    error_message = "This production root is bound to the existing insighthub-prod-cluster cluster."
  }
}

variable "vpc_id" {
  description = "VPC ID shared by the existing EKS cluster, RDS, and ElastiCache."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs in at least two Availability Zones."
  type        = set(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "At least two private subnet IDs are required for the RDS subnet group."
  }
}

variable "workload_security_group_ids" {
  description = "Security group IDs attached to EKS workloads allowed to reach PostgreSQL and Redis."
  type        = set(string)

  validation {
    condition     = length(var.workload_security_group_ids) > 0
    error_message = "At least one workload security group ID is required; CIDR-wide access is intentionally unsupported."
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
  description = "Required owner tag, for example a team name or student identifier."
  type        = string

  validation {
    condition     = trimspace(var.owner) != ""
    error_message = "owner must not be empty."
  }
}

variable "cost_center" {
  description = "Required cost-center tag."
  type        = string

  validation {
    condition     = trimspace(var.cost_center) != ""
    error_message = "cost_center must not be empty."
  }
}

variable "permissions_boundary_arn" {
  description = "Optional permissions boundary applied to the IRSA role."
  type        = string
  default     = null
}

variable "kms_key_arn" {
  description = "Optional existing KMS key ARN. When null, the module creates a dedicated rotating key."
  type        = string
  default     = null
}

variable "deletion_protection" {
  description = "Protect RDS from deletion. Keep false only for short-lived lab environments."
  type        = bool
  default     = false
}

variable "skip_final_snapshot" {
  description = "Skip the final RDS snapshot during lab teardown. Set false for retained production data."
  type        = bool
  default     = true
}
