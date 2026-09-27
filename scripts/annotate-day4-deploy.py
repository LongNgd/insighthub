"""Add a Grafana deploy marker after an approved Helm release is applied."""

import argparse
import base64
from datetime import datetime
import json
import os
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grafana-url", required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--time", required=True, help="Actual Helm release timestamp in RFC3339")
    args = parser.parse_args()
    timestamp = datetime.fromisoformat(args.time.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        parser.error("--time must include a timezone")
    token = os.environ.get("GRAFANA_API_TOKEN")
    user = os.environ.get("GRAFANA_USER")
    password = os.environ.get("GRAFANA_PASSWORD")
    if token:
        authorization = f"Bearer {token}"
    elif user and password:
        credential = base64.b64encode(f"{user}:{password}".encode()).decode()
        authorization = f"Basic {credential}"
    else:
        parser.error("set GRAFANA_API_TOKEN or GRAFANA_USER and GRAFANA_PASSWORD")
    payload = {
        "dashboardUID": "insighthub-day4",
        "time": int(timestamp.timestamp() * 1000),
        "tags": ["insighthub", "deploy"],
        "text": f"InsightHub Helm revision {args.revision}",
    }
    request = Request(
        args.grafana_url.rstrip("/") + "/api/annotations",
        data=json.dumps(payload).encode(),
        headers={"Authorization": authorization, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        result = json.load(response)
    print(json.dumps({"id": result["id"], "dashboardUID": payload["dashboardUID"],
                      "time": payload["time"]}))


if __name__ == "__main__":
    main()
