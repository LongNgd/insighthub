package main

import rego.v1

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_eks_cluster"
	not attribute_present_or_unknown(resource, "encryption_config")
	msg := sprintf("IH-EKS-001 %s must encrypt Kubernetes secrets", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_eks_cluster"
	not attribute_present_or_unknown(resource, "enabled_cluster_log_types")
	msg := sprintf("IH-EKS-001 %s must enable EKS control-plane logging", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_eks_cluster"
	vpc_config := object.get(after(resource), "vpc_config", [])[_]
	object.get(vpc_config, "endpoint_private_access", false) != true
	msg := sprintf("IH-EKS-001 %s must enable the private Kubernetes API endpoint", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_eks_cluster"
	vpc_config := object.get(after(resource), "vpc_config", [])[_]
	public_cidr := object.get(vpc_config, "public_access_cidrs", [])[_]
	public_cidr in {"0.0.0.0/0", "::/0"}
	msg := sprintf("IH-EKS-001 %s must not expose the Kubernetes API to the world", [resource.address])
}
