package main

import rego.v1

valid_node_max(value) if {
    is_number(value)
    value >= 1
    value <= 2
}

valid_db_storage(value) if {
    is_number(value)
    value >= 20
    value <= 50
}

valid_cache_nodes(value) if {
    is_number(value)
    value >= 1
    value <= 2
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_eks_node_group"
    configs := object.get(rc.change.after, "scaling_config", [])
    count(configs) == 0
    msg := sprintf("%s: EKS node scaling configuration is required", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_eks_node_group"
    max_size := object.get(rc.change.after.scaling_config[0], "max_size", null)
    not valid_node_max(max_size)
    msg := sprintf("%s: EKS node max_size exceeds lab limit 2", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_db_instance"
    storage := object.get(rc.change.after, "allocated_storage", null)
    not valid_db_storage(storage)
    msg := sprintf("%s: RDS allocated_storage must be 20-50 GiB", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type == "aws_elasticache_replication_group"
    nodes := object.get(rc.change.after, "num_cache_clusters", null)
    not valid_cache_nodes(nodes)
    msg := sprintf("%s: Redis node count exceeds lab limit 2", [rc.address])
}
