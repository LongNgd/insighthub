package main

import rego.v1

required_tags := {
	"project",
	"environment",
	"owner",
	"cost_center",
	"managed_by",
}

taggable_resource_types := {
	"aws_cloudwatch_log_group",
	"aws_db_instance",
	"aws_db_parameter_group",
	"aws_db_subnet_group",
	"aws_elasticache_parameter_group",
	"aws_elasticache_replication_group",
	"aws_elasticache_subnet_group",
	"aws_eip",
	"aws_eks_cluster",
	"aws_eks_node_group",
	"aws_flow_log",
	"aws_iam_openid_connect_provider",
	"aws_iam_role",
	"aws_internet_gateway",
	"aws_kms_key",
	"aws_launch_template",
	"aws_nat_gateway",
	"aws_route_table",
	"aws_secretsmanager_secret",
	"aws_security_group",
	"aws_subnet",
	"aws_vpc",
	"aws_vpc_security_group_ingress_rule",
}

active_managed_resource(resource) if {
	resource.mode == "managed"
	resource.change.actions != ["delete"]
}

after(resource) := object.get(resource.change, "after", {})

after_unknown(resource) := object.get(resource.change, "after_unknown", {})

nonempty_string(value) if {
	is_string(value)
	trim_space(value) != ""
}

attribute_present_or_unknown(resource, name) if {
	object.get(after(resource), name, null) != null
}

attribute_present_or_unknown(resource, name) if {
	name in object.keys(after_unknown(resource))
}

attribute_unknown(resource, name) if {
	name in object.keys(after_unknown(resource))
}

enabled(value) if {
	value == true
}

enabled(value) if {
	value == "true"
}

value_as_array(value) := value if {
	is_array(value)
}

value_as_array(value) := [value] if {
	not is_array(value)
}
