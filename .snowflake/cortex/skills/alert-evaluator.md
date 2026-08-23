---
name: alert-evaluator
description: Evaluate natural-language monitoring rules parsed by Cortex against live metering data.
---

# Smart Alert Evaluator

**Category:** ANALYSIS  
**Backing procedure:** `EVALUATE_SMART_ALERTS`

Evaluate natural-language monitoring rules parsed by Cortex against live metering data.

## Steps

1. Load active rules from SMART_ALERTS with their parsed metric, threshold and condition.
2. Compute the metric per warehouse, honouring an ANY-warehouse scope.
3. Apply the parsed condition (greater_than, less_than, equals).
4. Increment the trigger count and raise a notification when a rule trips.
5. Log every evaluation, tripped or not, so the trace shows the rule was checked.

## Why this way

Cortex parses the English once, at authoring time. Evaluation is then plain SQL, so a rule costs nothing per run and behaves identically every time.

## Trace

Every run writes one row per step to `FINOPS_GUARDIAN.PUBLIC.AGENT_EXECUTION_LOG`
keyed by `RUN_ID`, with `STATUS` moving RUNNING -> COMPLETED. The Operations tab
reads that table to stream this skill's reasoning as it happens, and the
Intelligence tab feeds recent runs to Cortex as grounding context.
