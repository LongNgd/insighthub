#!/usr/bin/env bash
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
POLICY="$ROOT/policy/terraform"
FIXTURES="$ROOT/tests/fixtures/terraform-plan"

conftest test --policy "$POLICY" "$FIXTURES/valid.json"

if invalid_output=$(conftest test --policy "$POLICY" "$FIXTURES/invalid.json" 2>&1); then
    printf '%s\n' 'FAIL: invalid plan unexpectedly passed' >&2
    exit 1
fi

for expected in 'missing required tag' 'RDS storage encryption' 'RDS Multi-AZ' 'Redis in-transit encryption' 'Redis automatic failover' 'Redis Multi-AZ' 'public EKS API must be disabled' 'public EKS API cannot allow' 'rotation resource is required' 'exceeds lab limit' 'destructive action'; do
    if ! printf '%s\n' "$invalid_output" | grep -q "$expected"; then
        printf 'FAIL: missing expected policy failure: %s\n' "$expected" >&2
        exit 1
    fi
done

printf '%s\n' 'PASS: valid Terraform plan accepted; invalid plan rejected across tags, security, cost and deletion.'
