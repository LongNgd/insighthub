package main

import rego.v1

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type in tagged_types
    after := object.get(rc.change, "after", {})
    tags := object.get(after, "tags_all", object.get(after, "tags", {}))
    some key in required_tags
    not nonempty(object.get(tags, key, ""))
    msg := sprintf("%s: missing required tag %s", [rc.address, key])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type in tagged_types
    after := object.get(rc.change, "after", {})
    tags := object.get(after, "tags_all", object.get(after, "tags", {}))
    object.get(tags, "environment", "") != "prod"
    msg := sprintf("%s: environment tag must be prod", [rc.address])
}

deny contains msg if {
    rc := input.resource_changes[_]
    active(rc)
    rc.type in tagged_types
    after := object.get(rc.change, "after", {})
    tags := object.get(after, "tags_all", object.get(after, "tags", {}))
    object.get(tags, "Class", "") != "DO2603"
    msg := sprintf("%s: Class tag must be DO2603", [rc.address])
}
