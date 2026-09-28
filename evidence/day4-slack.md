# Day 4 Slack delivery evidence

The user captured these unedited `#alerts` channel screenshots for the three
kind-only fixture incidents. Each contains the FIRING and RESOLVED messages.

| Incident | Alert | Started (UTC) | Resolved (UTC) | Screenshot |
| --- | --- | --- | --- | --- |
| 1 | InsightHubLLMLatencyAnomaly | 2026-09-28T18:18:43.827Z | 2026-09-28T18:24:43.827Z | [incident-1-latency-new.png](day4-slack/incident-1-latency-new.png) |
| 2 | InsightHubQueueDepthAnomaly | 2026-09-28T20:07:43.827Z | 2026-09-28T20:09:43.827Z | [incident-2-queue-new.png](day4-slack/incident-2-queue-new.png) |
| 3 | InsightHubHTTP5xxAnomaly | 2026-09-28T21:42:43.827Z | 2026-09-28T21:48:43.827Z | [incident-3-errors-new.png](day4-slack/incident-3-errors-new.png) |

All incidents were injected fixture faults on `kind-insighthub`; none indicates
a real LLM provider outage.
