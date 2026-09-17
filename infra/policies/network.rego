package main

import rego.v1

public_ipv4_cidrs := {"0.0.0.0/0"}
public_ipv6_cidrs := {"::/0"}
data_service_ports := {5432, 6379}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_db_instance"
	object.get(after(resource), "publicly_accessible", true) != false
	msg := sprintf("IH-NET-001 %s must not be publicly accessible", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_db_instance"
	not attribute_present_or_unknown(resource, "db_subnet_group_name")
	msg := sprintf("IH-NET-001 %s must use a private DB subnet group", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_db_instance"
	not attribute_present_or_unknown(resource, "vpc_security_group_ids")
	msg := sprintf("IH-NET-001 %s must use explicit VPC security groups", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_elasticache_replication_group"
	not attribute_present_or_unknown(resource, "subnet_group_name")
	msg := sprintf("IH-NET-001 %s must use a private ElastiCache subnet group", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_elasticache_replication_group"
	not attribute_present_or_unknown(resource, "security_group_ids")
	msg := sprintf("IH-NET-001 %s must use explicit VPC security groups", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type in {"aws_db_subnet_group", "aws_elasticache_subnet_group"}
	not attribute_unknown(resource, "subnet_ids")
	count(object.get(after(resource), "subnet_ids", [])) < 2
	msg := sprintf("IH-NET-001 %s must contain at least two private subnets", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type in {"aws_vpc_security_group_ingress_rule", "aws_security_group_rule"}
	object.get(after(resource), "cidr_ipv4", "") in public_ipv4_cidrs
	msg := sprintf("IH-NET-001 %s must not allow ingress from 0.0.0.0/0", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type in {"aws_vpc_security_group_ingress_rule", "aws_security_group_rule"}
	object.get(after(resource), "cidr_ipv6", "") in public_ipv6_cidrs
	msg := sprintf("IH-NET-001 %s must not allow ingress from ::/0", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_security_group_rule"
	cidr := object.get(after(resource), "cidr_blocks", [])[_]
	cidr in public_ipv4_cidrs
	msg := sprintf("IH-NET-001 %s must not allow ingress from 0.0.0.0/0", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type in {"aws_vpc_security_group_ingress_rule", "aws_security_group_rule"}
	object.get(after(resource), "from_port", 0) in data_service_ports
	not attribute_present_or_unknown(resource, "referenced_security_group_id")
	msg := sprintf("IH-NET-001 %s must allow data-service access by referenced security group only", [resource.address])
}
