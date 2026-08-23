---
name: cost-anomaly-detector
description: Find warehouses billing cloud-services credits while running zero compute.
---

# Cost Anomaly Detector

**Category:** DETECTION  
**Backing procedure:** `DETECT_IDLE_COMPUTE_DEMO / DETECT_IDLE_COMPUTE`

Find warehouses billing cloud-services credits while running zero compute.

## Steps

1. Load the metering window (demo table or ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY).
2. Isolate hours where CREDITS_USED_COMPUTE = 0 and CREDITS_USED_CLOUD_SERVICES > 0.
3. Score severity from the idle draw: >1.0 credits/hr HIGH, >0.1 MEDIUM, otherwise LOW.
4. Pick a remediation: SUSPEND_WAREHOUSE above 0.1 credits/hr, else SET_AUTO_SUSPEND.
5. Write new anomalies, skipping any warehouse-hour already recorded.

## Why this way

A warehouse that is up but not executing queries still bills cloud services. The compute/cloud-services split is the cleanest signal for it, and it needs no query history.

## Trace

Every run writes one row per step to `FINOPS_GUARDIAN.PUBLIC.AGENT_EXECUTION_LOG`
keyed by `RUN_ID`, with `STATUS` moving RUNNING -> COMPLETED. The Operations tab
reads that table to stream this skill's reasoning as it happens, and the
Intelligence tab feeds recent runs to Cortex as grounding context.
