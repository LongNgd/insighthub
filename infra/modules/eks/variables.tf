variable "cluster_name" {
  description = "Name of the EKS cluster."
  type        = string
}

variable "kubernetes_version" {
  description = "EKS Kubernetes control-plane version."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs used by the EKS control plane and managed nodes."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "EKS requires at least two private subnet IDs."
  }
}

variable "public_access_cidrs" {
  description = "Restricted IPv4 CIDRs allowed to reach the public Kubernetes API. Empty disables public access."
  type        = list(string)
  default     = []
}

variable "node_instance_types" {
  description = "EC2 instance types used by the managed node group."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "permissions_boundary_arn" {
  description = "Optional IAM permissions boundary for cluster and node roles."
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
}
