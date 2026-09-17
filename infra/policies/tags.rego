package main

import rego.v1

deny contains msg if {
	resource := input.resource_changes[_]
	active_managed_resource(resource)
	resource.type in taggable_resource_types
	tags := object.get(after(resource), "tags", {})
	some tag in required_tags
	not nonempty_string(object.get(tags, tag, ""))
	msg := sprintf("IH-TAG-001 %s must have a non-empty %q tag", [resource.address, tag])
}

