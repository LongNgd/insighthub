package main

import rego.v1

required_tags := ["project", "environment", "owner", "cost_center", "managed_by", "Class", "LabId", "Owner", "ExpiresAt"]

tagged_types := {
    "aws_eks_cluster",
    "aws_eks_node_group",
    "aws_db_instance",
    "aws_db_subnet_group",
    "aws_db_parameter_group",
    "aws_elasticache_replication_group",
    "aws_elasticache_subnet_group",
    "aws_security_group",
    "aws_kms_key",
    "aws_iam_role",
    "aws_secretsmanager_secret",
    "aws_cloudwatch_log_group",
}

has_action(rc, action) if {
    rc.change.actions[_] == action
}

active(rc) if {
    rc.mode == "managed"
    not has_action(rc, "delete")
}

nonempty(value) if {
    is_string(value)
    trim(value, " ") != ""
}

deny contains msg if {
    rc := input.resource_changes[_]
    rc.mode == "managed"
    has_action(rc, "delete")
    msg := sprintf("%s: destructive action requires separate review", [rc.address])
}
