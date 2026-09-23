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
    object.get(config, "endpoint_public_access", null) == true
    cidrs := object.get(config, "public_access_cidrs", [])
    count(cidrs) == 0
    msg := sprintf("%s: public EKS API needs explicit CIDRs", [rc.address])
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
