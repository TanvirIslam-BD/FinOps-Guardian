---
name: remediation-engine
description: Match each open anomaly to a toolkit action, then auto-apply it or queue it for a human.
---

# Remediation Engine

**Category:** REMEDIATION  
**Backing procedure:** `APPLY_FIXES / EXECUTE_REMEDIATION`

Match each open anomaly to a toolkit action, then auto-apply it or queue it for a human.

## Steps

1. Join open anomalies to REMEDIATION_ACTIONS on their recommended action.
2. Queue anything HIGH/CRITICAL or marked REQUIRES_APPROVAL, storing the rendered SQL for the approver.
3. Auto-apply the rest through EXECUTE_REMEDIATION.
4. Honour AGENT_CONFIG.DRY_RUN: record the statement as SIMULATED instead of executing it.
5. Write an audit row, a notification and a trace step for every decision.

## Why this way

The approver sees the exact statement that will run, not a template. DRY_RUN defaults to TRUE so installing the app can never alter a warehouse by surprise.

## Trace

Every run writes one row per step to `FINOPS_GUARDIAN.PUBLIC.AGENT_EXECUTION_LOG`
keyed by `RUN_ID`, with `STATUS` moving RUNNING -> COMPLETED. The Operations tab
reads that table to stream this skill's reasoning as it happens, and the
Intelligence tab feeds recent runs to Cortex as grounding context.
