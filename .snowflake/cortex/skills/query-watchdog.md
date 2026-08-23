---
name: query-watchdog
description: Flag queries past their runtime budget and attribute them to a user and role.
---

# Query Watchdog

**Category:** DETECTION  
**Backing procedure:** `DETECT_LONG_RUNNING_QUERIES`

Flag queries past their runtime budget and attribute them to a user and role.

## Steps

1. Scan query history for statements exceeding the runtime budget (default 600s).
2. Attach warehouse, user, role and the leading 200 characters of query text.
3. Grade severity: over 30 minutes is HIGH, otherwise MEDIUM.
4. Route HIGH findings to CANCEL_QUERY and the rest to FLAG_QUERY_FOR_REVIEW.

## Why this way

Cancelling someone's query is disruptive, so only sustained overruns propose cancellation and both routes require approval. Naming the user and role is what makes the finding actionable.

## Trace

Every run writes one row per step to `FINOPS_GUARDIAN.PUBLIC.AGENT_EXECUTION_LOG`
keyed by `RUN_ID`, with `STATUS` moving RUNNING -> COMPLETED. The Operations tab
reads that table to stream this skill's reasoning as it happens, and the
Intelligence tab feeds recent runs to Cortex as grounding context.
