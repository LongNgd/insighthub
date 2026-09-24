#!/usr/bin/env python3
"""Run the existing smoke contract with Day 1's strict asynchronous upload check."""

import json
import sys

from verify import Failed, Incomplete, parser, smoke


def main() -> int:
    args = parser().parse_args(["smoke", *sys.argv[1:]])
    args.repo = args.repo.resolve()
    try:
        result = smoke(args, async_required=True)
    except (Failed, Incomplete) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
