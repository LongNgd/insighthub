"""Exercise the Day 3 Conftest gate with valid and isolated unsafe plans."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import pytest


REPO_ROOT = Path(
    os.environ.get("INSIGHTHUB_REPO_ROOT", Path(__file__).resolve().parents[3])
).resolve()
POLICY_DIR = REPO_ROOT / "policy" / "terraform"
VALID_PLAN = REPO_ROOT / "tests" / "fixtures" / "terraform-plan" / "valid.json"


def _check_plan(path: Path) -> tuple[int, list[dict[str, Any]]]:
    result = subprocess.run(
        ["conftest", "test", "--output", "json", "--policy", str(POLICY_DIR), str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout.strip(), result.stderr
    reports = json.loads(result.stdout)
    assert isinstance(reports, list) and len(reports) == 1
    return result.returncode, reports


def test_policy_allows_valid() -> None:
    plan = json.loads(VALID_PLAN.read_text(encoding="utf-8"))
    addresses = {change["address"] for change in plan["resource_changes"]}
    assert {
        "aws_eks_cluster.this",
        "aws_eks_node_group.this",
        "aws_db_instance.this",
        "aws_elasticache_replication_group.this",
        "aws_secretsmanager_secret.redis",
        "aws_secretsmanager_secret_rotation.redis",
    } <= addresses
    assert all(change["change"]["actions"] == ["create"] for change in plan["resource_changes"])

    exit_code, reports = _check_plan(VALID_PLAN)
    assert exit_code == 0
    assert reports[0].get("successes", 0) > 0
    assert not reports[0].get("failures")


@pytest.mark.parametrize(
    ("address", "path", "unsafe_value", "expected_deny"),
    [
        (
            "aws_db_instance.this",
            ("change", "after", "tags_all", "owner"),
            None,
            "missing required tag owner",
        ),
        (
            "aws_eks_cluster.this",
            ("change", "after", "vpc_config", 0, "endpoint_public_access"),
            True,
            "public EKS API must be disabled",
        ),
        (
            "aws_db_instance.this",
            ("change", "after", "storage_encrypted"),
            False,
            "RDS storage encryption is required",
        ),
        (
            "aws_elasticache_replication_group.this",
            ("change", "after", "transit_encryption_enabled"),
            False,
            "Redis in-transit encryption is required",
        ),
        (
            "aws_eks_node_group.this",
            ("change", "after", "scaling_config", 0, "max_size"),
            3,
            "EKS node max_size exceeds lab limit 2",
        ),
        (
            "aws_db_instance.this",
            ("change", "actions"),
            ["delete"],
            "destructive action requires separate review",
        ),
    ],
)
def test_policy_denies_unsafe(
    tmp_path: Path,
    address: str,
    path: tuple[str | int, ...],
    unsafe_value: Any,
    expected_deny: str,
) -> None:
    plan = deepcopy(json.loads(VALID_PLAN.read_text(encoding="utf-8")))
    change = next(item for item in plan["resource_changes"] if item["address"] == address)
    target = change
    for key in path[:-1]:
        target = target[key]
    if unsafe_value is None:
        target.pop(path[-1])
    else:
        target[path[-1]] = unsafe_value

    unsafe_plan = tmp_path / "unsafe-plan.json"
    unsafe_plan.write_text(json.dumps(plan), encoding="utf-8")
    exit_code, reports = _check_plan(unsafe_plan)
    messages = [failure["msg"] for failure in reports[0].get("failures", [])]
    assert exit_code != 0
    assert any(message.startswith(f"{address}:") and expected_deny in message for message in messages)
