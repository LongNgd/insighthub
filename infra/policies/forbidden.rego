package main

import rego.v1

forbidden_resource_types := {
	"aws_eks_cluster",
	"aws_eks_node_group",
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type in forbidden_resource_types
	msg := sprintf("IH-EKS-001 %s is forbidden because the EKS cluster already exists", [resource.address])
}

