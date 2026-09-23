variable "aws_region" {
  description = "AWS region for this lab run."
  type        = string
}

variable "aws_account_id" {
  description = "Sandbox account ID; the provider refuses any other account."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain 12 digits."
  }
}

variable "vpc_id" {
  description = "Existing lab VPC ID. Its lifecycle is managed separately."
  type        = string
}

variable "private_subnet_ids" {
  description = "At least two private subnets in different availability zones."
  type        = list(string)

  validation {
    condition     = length(distinct(var.private_subnet_ids)) >= 2
    error_message = "Provide at least two distinct private subnet IDs."
  }
}

variable "eks_api_cidrs" {
  description = "Restricted CIDRs allowed to reach the EKS public API endpoint."
  type        = list(string)

  validation {
    condition     = length(var.eks_api_cidrs) > 0 && !contains(var.eks_api_cidrs, "0.0.0.0/0")
    error_message = "Provide explicit API CIDRs; unrestricted access is forbidden."
  }
}

variable "owner" {
  description = "Owner tag for all supported resources."
  type        = string
}

variable "cost_center" {
  description = "Cost center tag for all supported resources."
  type        = string
}

variable "lab_id" {
  description = "Unique ID for the bounded AWS lab run."
  type        = string
}

variable "expires_at" {
  description = "Lab expiration timestamp recorded in tags and manifest."
  type        = string
}

variable "node_instance_type" {
  description = "EKS node EC2 type, chosen after the cost review."
  type        = string
}

variable "db_instance_class" {
  description = "RDS instance class, chosen after the cost review."
  type        = string
}

variable "cache_node_type" {
  description = "ElastiCache node type, chosen after the cost review."
  type        = string
}

variable "redis_auth_token" {
  description = "Redis AUTH token from a secure external input. Never commit a tfvars file."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.redis_auth_token) >= 16 && length(var.redis_auth_token) <= 128
    error_message = "Redis AUTH token length must be 16 to 128 characters."
  }
}

variable "manage_namespace" {
  description = "Enable only after EKS and its node group are ready."
  type        = bool
  default     = false
}
