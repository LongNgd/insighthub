"""Contract tests for the Day 3 Terraform plan policy gate."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


REQUIRED_POLICY_IDS = {
    "IH-TAG-001",
    "IH-ENC-001",
    "IH-NET-001",
    "IH-IAM-001",
    "IH-COST-001",
    "IH-EKS-001",
}

REQUIRED_UNSAFE_DETAILS = {
    "must enable RDS storage encryption",
    "must not be publicly accessible",
    "must not grant wildcard service actions",
    "trust must be restricted to the InsightHub ServiceAccount",
    "must use db.t3.small for the lab",
    "must use cache.t3.micro for the lab",
}


def _repo_root() -> Path:
    configured = os.environ.get("INSIGHTHUB_REPO_ROOT")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[3]


def _run_conftest(fixture_name: str) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("conftest")
    assert executable is not None, "conftest executable is required for Day 3 policy tests"

    root = _repo_root()
    fixture = Path(__file__).with_name("fixtures") / fixture_name
    policies = root / "infra" / "policies"
    assert fixture.is_file(), f"missing Terraform plan fixture: {fixture}"
    assert policies.is_dir(), f"missing Conftest policy directory: {policies}"

    return subprocess.run(
        [
            executable,
            "test",
            str(fixture),
            "--policy",
            str(policies),
            "--output",
            "json",
        ],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


def _diagnostic(result: subprocess.CompletedProcess[str]) -> str:
    return f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def test_policy_allows_valid() -> None:
    result = _run_conftest("valid-plan.json")
    assert result.returncode == 0, _diagnostic(result)


def test_policy_denies_unsafe() -> None:
    result = _run_conftest("unsafe-plan.json")
    combined_output = result.stdout + result.stderr

    assert result.returncode != 0, "unsafe Terraform plan unexpectedly passed Conftest"
    missing = sorted(policy_id for policy_id in REQUIRED_POLICY_IDS if policy_id not in combined_output)
    assert not missing, f"unsafe plan did not exercise policy IDs {missing}\n{_diagnostic(result)}"
    missing_details = sorted(
        detail for detail in REQUIRED_UNSAFE_DETAILS if detail not in combined_output
    )
    assert not missing_details, (
        f"unsafe plan did not exercise policy details {missing_details}\n{_diagnostic(result)}"
    )
