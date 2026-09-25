#!/usr/bin/env python3
"""Create the local kind runtime Secret without putting credentials in argv or Git."""

import json
import secrets
import subprocess
import sys


CONTEXT = "kind-insighthub"
NAMESPACE = "insighthub-prod"
NAME = "insighthub-local-credentials"


def kubectl(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", "--context", CONTEXT, "-n", NAMESPACE, *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    context = subprocess.run(
        ["kubectl", "config", "current-context"],
        text=True,
        capture_output=True,
        check=False,
    )
    if context.returncode or context.stdout.strip() != CONTEXT:
        print(f"Select the {CONTEXT} admin context before creating a local Secret.", file=sys.stderr)
        return 2

    existing = kubectl("get", "secret", NAME, "-o", "name")
    if existing.returncode == 0:
        print(f"Secret {NAMESPACE}/{NAME} already exists; credentials were not rotated.")
        return 0
    if "NotFound" not in existing.stderr and "not found" not in existing.stderr:
        print("Could not check the local Secret; verify kind access.", file=sys.stderr)
        return 2

    postgres_pvc = kubectl("get", "pvc", "insighthub-postgres-data", "-o", "name")
    if postgres_pvc.returncode == 0:
        print("PostgreSQL PVC exists without its Secret; recover credentials before proceeding.", file=sys.stderr)
        return 2
    if "NotFound" not in postgres_pvc.stderr and "not found" not in postgres_pvc.stderr:
        print("Could not check PostgreSQL PVC; verify kind access.", file=sys.stderr)
        return 2

    postgres_password = secrets.token_hex(24)
    redis_password = secrets.token_hex(24)
    manifest = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": NAME, "namespace": NAMESPACE},
        "type": "Opaque",
        "stringData": {
            "postgres-password": postgres_password,
            "redis-password": redis_password,
            "database-url": (
                f"postgresql://insighthub:{postgres_password}@insighthub-postgres:5432/insighthub"
            ),
            "redis-url": f"redis://:{redis_password}@insighthub-redis:6379/0",
            "redis.conf": f"appendonly yes\ndir /data\nrequirepass {redis_password}\n",
        },
    }
    created = kubectl("create", "-f", "-", input_text=json.dumps(manifest))
    if created.returncode:
        print("Could not create the local Secret; check kind access and namespace.", file=sys.stderr)
        return 2
    print(f"Created Secret {NAMESPACE}/{NAME} with random local credentials.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
