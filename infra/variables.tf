variable "aws_region" {
  description = "AWS region where the complete InsightHub stack is created."
  type        = string
  default     = "ap-southeast-1"
}

variable "aws_profile" {
  description = "Optional local AWS profile. Leave empty in GitHub Actions/OIDC."
  type        = string
  default     = ""
}

variable "eks_cluster_name" {
  description = "Name of the EKS cluster created for InsightHub."
  type        = string
  default     = "insighthub-prod-cluster"
}

variable "vpc_cidr" {
  description = "CIDR block for the dedicated InsightHub VPC."
  type        = string
  default     = "10.42.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid IPv4 CIDR block."
  }
}

variable "eks_public_access_cidrs" {
  description = "Approved operator/CI IPv4 CIDRs allowed to reach the public EKS API. Empty disables the public endpoint. Never use 0.0.0.0/0."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for cidr in var.eks_public_access_cidrs : can(cidrnetmask(cidr)) && cidr != "0.0.0.0/0"
    ])
    error_message = "eks_public_access_cidrs must contain valid restricted IPv4 CIDRs and must not contain 0.0.0.0/0."
  }
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version approved for the lab."
  type        = string
  default     = "1.33"
}

variable "eks_node_instance_types" {
  description = "Instance types for the private EKS managed node group."
  type        = list(string)
  default     = ["t3.medium"]
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
  default     = "Nguyen Dinh Long"

  validation {
    condition     = trimspace(var.owner) != ""
    error_message = "owner must not be empty."
  }
}

variable "cost_center" {
  description = "Required cost-center tag."
  type        = string
  default     = "do2603-lab"

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
