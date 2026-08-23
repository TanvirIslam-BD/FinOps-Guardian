---
name: remediation-approver
description: Execute an approved remediation and record who approved it, through which channel.
---

# Remediation Approver

**Category:** REMEDIATION  
**Backing procedure:** `APPROVE_FIX / REJECT_FIX / CONSUME_APPROVAL_TOKEN`

Execute an approved remediation and record who approved it, through which channel.

## Steps

1. Verify a PENDING_APPROVAL audit row exists for the anomaly.
2. Accept an action override when the approver picks a different toolkit action.
3. Execute through EXECUTE_REMEDIATION and close the anomaly.
4. Stamp the audit row with the approver and channel (UI, EMAIL or AUTO).
5. Burn any approval token still outstanding for that anomaly.

## Why this way

Approval and execution are one transaction path, so the audit trail can never show an approval whose remediation silently did not run. Email tokens are single-use and expiring.

## Trace

Every run writes one row per step to `FINOPS_GUARDIAN.PUBLIC.AGENT_EXECUTION_LOG`
keyed by `RUN_ID`, with `STATUS` moving RUNNING -> COMPLETED. The Operations tab
reads that table to stream this skill's reasoning as it happens, and the
Intelligence tab feeds recent runs to Cortex as grounding context.
