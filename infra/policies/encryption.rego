package main

import rego.v1

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_db_instance"
	object.get(after(resource), "storage_encrypted", false) != true
	msg := sprintf("IH-ENC-001 %s must enable RDS storage encryption", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_db_instance"
	not attribute_present_or_unknown(resource, "kms_key_id")
	msg := sprintf("IH-ENC-001 %s must use a KMS key for RDS storage", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_elasticache_replication_group"
	object.get(after(resource), "at_rest_encryption_enabled", false) != true
	msg := sprintf("IH-ENC-001 %s must enable Redis encryption at rest", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_elasticache_replication_group"
	object.get(after(resource), "transit_encryption_enabled", false) != true
	msg := sprintf("IH-ENC-001 %s must enable Redis encryption in transit", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_elasticache_replication_group"
	object.get(after(resource), "transit_encryption_mode", "") != "required"
	msg := sprintf("IH-ENC-001 %s must require Redis transit encryption", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_elasticache_replication_group"
	not attribute_present_or_unknown(resource, "kms_key_id")
	msg := sprintf("IH-ENC-001 %s must use a KMS key for Redis", [resource.address])
}

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type == "aws_secretsmanager_secret"
	not attribute_present_or_unknown(resource, "kms_key_id")
	msg := sprintf("IH-ENC-001 %s must use a KMS key for Secrets Manager", [resource.address])
}

