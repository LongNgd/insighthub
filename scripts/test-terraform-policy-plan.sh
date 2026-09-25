#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ $# -ne 1 || ! -f $1 ]]; then
    printf 'Usage: %s /absolute/path/to/real.tfplan\n' "$0" >&2
    exit 2
fi

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PLAN=$(realpath -- "$1")
PLAN_JSON=$(mktemp "${TMPDIR:-/tmp}/insighthub-day3-plan.XXXXXXXX.json")
trap 'rm -f -- "$PLAN_JSON"' EXIT

terraform -chdir="$ROOT/infra" show -json "$PLAN" > "$PLAN_JSON"
conftest test --policy "$ROOT/policy/terraform" "$PLAN_JSON"
printf '%s\n' 'PASS: Conftest accepted the Terraform binary plan; temporary JSON was removed.'
