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
	"aws_db_instance",
	"aws_db_parameter_group",
	"aws_db_subnet_group",
	"aws_elasticache_parameter_group",
	"aws_elasticache_replication_group",
	"aws_elasticache_subnet_group",
	"aws_iam_role",
	"aws_kms_key",
	"aws_secretsmanager_secret",
	"aws_security_group",
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

value_as_array(value) := value if {
	is_array(value)
}

value_as_array(value) := [value] if {
	not is_array(value)
}

