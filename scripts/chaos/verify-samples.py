#!/usr/bin/env python3
"""Check every RCA citation against the local Prometheus query_range API."""

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen


def epoch(value: str) -> float:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("RCA timestamp has no timezone")
    return timestamp.timestamp()


def verify(path: Path, prometheus_url: str) -> int:
    parsed = urlsplit(prometheus_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Prometheus must use an HTTP localhost port-forward")
    report = json.loads(path.read_text(encoding="utf-8"))
    start, end = epoch(report["started_at"]), epoch(report["ended_at"])
    if start >= end or not report["samples"]:
        raise ValueError("Invalid RCA window or empty samples")
    for sample in report["samples"]:
        at = epoch(sample["timestamp"])
        if not start <= at <= end:
            raise ValueError("RCA sample falls outside incident window")
        selector = sample["metric"]
        if sample["labels"]:
            selector += "{" + ",".join(
                f"{key}={json.dumps(value)}"
                for key, value in sorted(sample["labels"].items())
            ) + "}"
        query = urlencode({"query": selector, "start": at, "end": at + 1, "step": 1})
        with urlopen(prometheus_url.rstrip("/") + "/api/v1/query_range?" + query, timeout=15) as response:
            body = json.load(response)
        if body.get("status") != "success" or body.get("data", {}).get("resultType") != "matrix":
            raise ValueError("Prometheus range query failed")
        expected = float(sample["value"])
        if not math.isfinite(expected):
            raise ValueError("Non-finite RCA sample")
        matched = any(
            abs(float(timestamp) - at) < 1
            and math.isclose(float(value), expected, rel_tol=1e-6, abs_tol=1e-9)
            for series in body["data"]["result"]
            for timestamp, value in series["values"]
        )
        if not matched:
            raise ValueError(f"RCA citation does not match Prometheus: {sample['metric']} at {sample['timestamp']}")
    return len(report["samples"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:19090")
    args = parser.parse_args()
    count = verify(args.report, args.prometheus_url)
    print(f"PASS: {count} RCA samples match live Prometheus query_range")


if __name__ == "__main__":
    main()
