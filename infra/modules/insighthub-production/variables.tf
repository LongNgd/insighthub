variable "cluster_name" {
  description = "Name of the existing EKS cluster. The module does not create or modify the cluster."
  type        = string
}

variable "cluster_oidc_issuer_url" {
  description = "OIDC issuer URL reported by the existing EKS cluster."
  type        = string

  validation {
    condition     = startswith(var.cluster_oidc_issuer_url, "https://")
    error_message = "cluster_oidc_issuer_url must be an HTTPS URL."
  }
}

variable "cluster_oidc_provider_arn" {
  description = "ARN of the IAM OIDC provider already associated with the EKS cluster."
  type        = string
}

variable "namespace" {
  description = "Kubernetes namespace for InsightHub."
  type        = string
  default     = "insighthub"
}

variable "service_account_name" {
  description = "IRSA-enabled Kubernetes ServiceAccount used by InsightHub pods."
  type        = string
  default     = "insighthub"
}

variable "vpc_id" {
  description = "VPC containing the existing EKS cluster and private data subnets."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs spanning at least two Availability Zones."
  type        = set(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "private_subnet_ids must contain at least two subnets."
  }
}

variable "workload_security_group_ids" {
  description = "EKS workload security groups permitted to reach RDS and Redis."
  type        = set(string)

  validation {
    condition     = length(var.workload_security_group_ids) > 0
    error_message = "At least one workload security group ID is required."
  }
}

variable "permissions_boundary_arn" {
  description = "Optional permissions boundary for the IRSA role."
  type        = string
  default     = null
}

variable "kms_key_arn" {
  description = "Optional customer-managed KMS key ARN. A dedicated rotating key is created when null."
  type        = string
  default     = null
}

variable "tags" {
  description = "Required ownership and cost-allocation tags."
  type = object({
    project     = string
    environment = string
    owner       = string
    cost_center = string
  })

  validation {
    condition = alltrue([
      for value in values(var.tags) : trimspace(value) != ""
    ])
    error_message = "project, environment, owner, and cost_center tags must all be non-empty."
  }
}

variable "postgres_engine_version" {
  description = "Pinned RDS PostgreSQL 16 minor version."
  type        = string
  default     = "16.15"

  validation {
    condition     = startswith(var.postgres_engine_version, "16.")
    error_message = "InsightHub requires a PostgreSQL 16 minor version."
  }
}

variable "rds_instance_class" {
  description = "RDS instance class. Lab default required by the assignment."
  type        = string
  default     = "db.t3.small"
}

variable "rds_allocated_storage_gib" {
  description = "Initial GP3 storage size in GiB."
  type        = number
  default     = 20

  validation {
    condition     = var.rds_allocated_storage_gib >= 20
    error_message = "RDS GP3 storage must be at least 20 GiB."
  }
}

variable "rds_backup_retention_days" {
  description = "Automated backup retention. Keep short for a disposable lab."
  type        = number
  default     = 1

  validation {
    condition     = var.rds_backup_retention_days >= 1 && var.rds_backup_retention_days <= 35
    error_message = "RDS backup retention must be between 1 and 35 days."
  }
}

variable "deletion_protection" {
  description = "Enable RDS deletion protection. Defaults to false for controlled lab teardown."
  type        = bool
  default     = false
}

variable "skip_final_snapshot" {
  description = "Skip final snapshot on destroy. Defaults to true for reproducible lab data."
  type        = bool
  default     = true
}

variable "redis_engine_version" {
  description = "Pinned ElastiCache Redis OSS major/minor version."
  type        = string
  default     = "7.1"
}

variable "redis_node_type" {
  description = "ElastiCache node type. Lab default required by the assignment."
  type        = string
  default     = "cache.t3.micro"
}
