---
name: warehouse-optimizer
description: Recommend downsizing warehouses whose peak demand never approaches provisioned capacity.
---

# Warehouse Optimizer

**Category:** DETECTION  
**Backing procedure:** `DETECT_OVERSIZED_WAREHOUSE`

Recommend downsizing warehouses whose peak demand never approaches provisioned capacity.

## Steps

1. Read provisioned size and per-hour credit capacity for each warehouse.
2. Take the peak hourly credit draw across the metering window.
3. Flag warehouses under the utilisation floor (default 40%); below 20% is HIGH.
4. Estimate recovery as the difference between current spend and spend at one size down.
5. Propose SCALE_DOWN_WAREHOUSE with the next size down as the action parameter.

## Why this way

Peak, not average, is the safe basis for a downsize: a warehouse must still absorb its busiest hour after resizing. Every step down halves the credit rate, so one step is worth about 50%.

## Trace

Every run writes one row per step to `FINOPS_GUARDIAN.PUBLIC.AGENT_EXECUTION_LOG`
keyed by `RUN_ID`, with `STATUS` moving RUNNING -> COMPLETED. The Operations tab
reads that table to stream this skill's reasoning as it happens, and the
Intelligence tab feeds recent runs to Cortex as grounding context.
