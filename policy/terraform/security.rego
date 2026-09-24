package main

import rego.v1

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_db_instance"
    object.get(rc.change.after, "storage_encrypted", null) != true
    msg := sprintf("%s: RDS storage encryption is required", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_db_instance"
    object.get(rc.change.after, "publicly_accessible", null) != false
    msg := sprintf("%s: RDS must be private", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_db_instance"
    object.get(rc.change.after, "multi_az", null) != true
    msg := sprintf("%s: RDS Multi-AZ is required", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_db_instance"
    object.get(rc.change.after, "deletion_protection", null) != true
    msg := sprintf("%s: RDS deletion protection is required outside teardown", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_elasticache_replication_group"
    object.get(rc.change.after, "at_rest_encryption_enabled", null) != true
    msg := sprintf("%s: Redis at-rest encryption is required", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_elasticache_replication_group"
    object.get(rc.change.after, "transit_encryption_enabled", null) != true
    msg := sprintf("%s: Redis in-transit encryption is required", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_elasticache_replication_group"
    object.get(rc.change.after, "automatic_failover_enabled", null) != true
    msg := sprintf("%s: Redis automatic failover is required", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_elasticache_replication_group"
    object.get(rc.change.after, "multi_az_enabled", null) != true
    msg := sprintf("%s: Redis Multi-AZ is required", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_eks_cluster"
    configs := object.get(rc.change.after, "encryption_config", [])
    count(configs) == 0
    msg := sprintf("%s: EKS secrets encryption is required", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_eks_cluster"
    configs := object.get(rc.change.after, "vpc_config", [])
    count(configs) == 0
    msg := sprintf("%s: EKS endpoint configuration is required", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_eks_cluster"
    config := rc.change.after.vpc_config[0]
    object.get(config, "endpoint_private_access", null) != true
    msg := sprintf("%s: private EKS API access is required", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_eks_cluster"
    config := rc.change.after.vpc_config[0]
    object.get(config, "endpoint_public_access", null) != false
    msg := sprintf("%s: public EKS API must be disabled", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_eks_cluster"
    config := rc.change.after.vpc_config[0]
    object.get(config, "endpoint_public_access", null) == true
    cidrs := object.get(config, "public_access_cidrs", [])
    count(cidrs) == 0
    msg := sprintf("%s: public EKS API needs explicit CIDRs", [rc.address])
}

has_rotation if {
    rc := input.resource_changes[_]
    active(rc)
    rc.address == "aws_secretsmanager_secret_rotation.redis"
    rc.type == "aws_secretsmanager_secret_rotation"
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.address == "aws_secretsmanager_secret_rotation.redis"
    rules := object.get(rc.change.after, "rotation_rules", [])
    count(rules) == 0
    msg := sprintf("%s: Redis rotation schedule is required", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.address == "aws_secretsmanager_secret_rotation.redis"
    rules := object.get(rc.change.after, "rotation_rules", [])
    count(rules) > 0
    days := object.get(rules[0], "automatically_after_days", null)
    not valid_rotation_days(days)
    msg := sprintf("%s: Redis rotation interval must be 1-30 days", [rc.address])
}

valid_rotation_days(days) if {
    is_number(days)
    days >= 1
    days <= 30
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.address == "aws_secretsmanager_secret.redis"
    not has_rotation
    msg := sprintf("%s: Redis secret rotation resource is required", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_eks_cluster"
    config := rc.change.after.vpc_config[0]
    object.get(config, "endpoint_public_access", null) == true
    cidr := config.public_access_cidrs[_]
    cidr in {"0.0.0.0/0", "::/0"}
    msg := sprintf("%s: public EKS API cannot allow %s", [rc.address, cidr])
}
