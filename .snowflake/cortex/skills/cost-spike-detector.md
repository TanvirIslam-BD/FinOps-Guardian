---
name: cost-spike-detector
description: Catch hours where credit burn jumps well above a warehouse's own recent baseline.
---

# Cost Spike Detector

**Category:** DETECTION  
**Backing procedure:** `DETECT_COST_SPIKE_DEMO`

Catch hours where credit burn jumps well above a warehouse's own recent baseline.

## Steps

1. Compute a trailing 3-hour rolling average per warehouse, excluding the hour under test.
2. Require at least 2 preceding hours so a cold start cannot look like a spike.
3. Flag hours at or above the threshold multiple (default 2.5x).
4. Grade severity by multiple: >8x CRITICAL, >4x HIGH, otherwise MEDIUM.
5. Route CRITICAL spikes to SET_RESOURCE_MONITOR and the rest to SET_STATEMENT_TIMEOUT.

## Why this way

Each warehouse is compared against itself, so a large ETL warehouse is not judged by the same absolute number as a small dev one.

## Trace

Every run writes one row per step to `FINOPS_GUARDIAN.PUBLIC.AGENT_EXECUTION_LOG`
keyed by `RUN_ID`, with `STATUS` moving RUNNING -> COMPLETED. The Operations tab
reads that table to stream this skill's reasoning as it happens, and the
Intelligence tab feeds recent runs to Cortex as grounding context.
