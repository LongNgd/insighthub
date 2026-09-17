package main

import rego.v1

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type in {"aws_iam_user", "aws_iam_access_key"}
	msg := sprintf("IH-IAM-001 %s is forbidden; use OIDC or IRSA instead", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type in {"aws_iam_policy", "aws_iam_role_policy"}
	raw_policy := object.get(after(resource), "policy", "")
	nonempty_string(raw_policy)
	document := json.unmarshal(raw_policy)
	statement := value_as_array(object.get(document, "Statement", []))[_]
	action := value_as_array(object.get(statement, "Action", []))[_]
	is_string(action)
	endswith(action, ":*")
	msg := sprintf("IH-IAM-001 %s must not grant wildcard service actions (%s)", [resource.address, action])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type in {"aws_iam_policy", "aws_iam_role_policy"}
	raw_policy := object.get(after(resource), "policy", "")
	nonempty_string(raw_policy)
	document := json.unmarshal(raw_policy)
	statement := value_as_array(object.get(document, "Statement", []))[_]
	action := value_as_array(object.get(statement, "Action", []))[_]
	action == "*"
	msg := sprintf("IH-IAM-001 %s must not grant Action *", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type in {"aws_iam_policy", "aws_iam_role_policy"}
	raw_policy := object.get(after(resource), "policy", "")
	nonempty_string(raw_policy)
	document := json.unmarshal(raw_policy)
	statement := value_as_array(object.get(document, "Statement", []))[_]
	policy_resource := value_as_array(object.get(statement, "Resource", []))[_]
	policy_resource == "*"
	msg := sprintf("IH-IAM-001 %s must not grant access to Resource *", [resource.address])
}

workload_role(resource) if {
	resource.type == "aws_iam_role"
	endswith(resource.address, "aws_iam_role.workload")
}

known_assume_role_policy(resource) if {
	nonempty_string(object.get(after(resource), "assume_role_policy", ""))
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	workload_role(resource)
	known_assume_role_policy(resource)
	policy := object.get(after(resource), "assume_role_policy", "")
	not contains(policy, "sts:AssumeRoleWithWebIdentity")
	msg := sprintf("IH-IAM-001 %s must trust sts:AssumeRoleWithWebIdentity", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	workload_role(resource)
	known_assume_role_policy(resource)
	policy := object.get(after(resource), "assume_role_policy", "")
	not contains(policy, "system:serviceaccount:insighthub:insighthub")
	msg := sprintf("IH-IAM-001 %s trust must be restricted to the InsightHub ServiceAccount", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	workload_role(resource)
	known_assume_role_policy(resource)
	policy := object.get(after(resource), "assume_role_policy", "")
	not contains(policy, "sts.amazonaws.com")
	msg := sprintf("IH-IAM-001 %s trust must validate the sts.amazonaws.com audience", [resource.address])
}

