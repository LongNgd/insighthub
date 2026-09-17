package main

import rego.v1

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_db_instance"
	object.get(after(resource), "instance_class", "") != "db.t3.small"
	msg := sprintf("IH-COST-001 %s must use db.t3.small for the lab", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_db_instance"
	object.get(after(resource), "engine", "") != "postgres"
	msg := sprintf("IH-COST-001 %s must use PostgreSQL", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_db_instance"
	not startswith(object.get(after(resource), "engine_version", ""), "16.")
	msg := sprintf("IH-COST-001 %s must use PostgreSQL 16", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_db_instance"
	object.get(after(resource), "storage_type", "") != "gp3"
	msg := sprintf("IH-COST-001 %s must use GP3 storage", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_db_instance"
	object.get(after(resource), "allocated_storage", 0) != 20
	msg := sprintf("IH-COST-001 %s must use 20 GiB for the lab", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_db_instance"
	object.get(after(resource), "multi_az", true) != false
	msg := sprintf("IH-COST-001 %s must remain single-AZ for the lab", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_elasticache_replication_group"
	object.get(after(resource), "node_type", "") != "cache.t3.micro"
	msg := sprintf("IH-COST-001 %s must use cache.t3.micro for the lab", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_elasticache_replication_group"
	object.get(after(resource), "engine", "") != "redis"
	msg := sprintf("IH-COST-001 %s must use Redis OSS", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_elasticache_replication_group"
	not startswith(object.get(after(resource), "engine_version", ""), "7.")
	msg := sprintf("IH-COST-001 %s must use Redis 7", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_elasticache_replication_group"
	object.get(after(resource), "num_cache_clusters", 0) != 1
	msg := sprintf("IH-COST-001 %s must use exactly one cache node for the lab", [resource.address])
}

