# Plan: Hackathon Feedback Enhancements

## Overview

Implement all 4 feedback recommendations from the hackathon judges to make FinOps Guardian more intelligent, transparent, and actionable.

---

## Feedback 1: Enhanced Natural Language Reasoning

**Current state:** The AI chat sends only the `USAGE_ANOMALIES` table (15 rows) as context. Responses are generic.

**Enhancement:** Enrich the AI prompt with:
- **Query history** from `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` — top expensive queries by warehouse, user, role
- **Warehouse metering** breakdown — credits by hour/day for the relevant warehouse
- **User attribution** — which users/roles drove the cost
- **Smart Alerts context** — active alert rules and their triggers

This way the AI can say "The cost spike on ANALYTICS_WH was caused by user JOHN_DOE running 3 full-table scans on ORDERS (query IDs: ...) between 2-4 AM" instead of just "There was a cost spike."

**Implementation:**
```python
# Before calling CORTEX.COMPLETE, gather richer context:
query_context = run_query_cached(session, """
    SELECT USER_NAME, ROLE_NAME, WAREHOUSE_NAME, 
           ROUND(TOTAL_ELAPSED_TIME/1000,1) AS SECONDS,
           ROUND(CREDITS_USED_CLOUD_SERVICES,4) AS CREDITS,
           QUERY_TYPE, LEFT(QUERY_TEXT, 200) AS QUERY_PREVIEW
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
    ORDER BY CREDITS_USED_CLOUD_SERVICES DESC LIMIT 10
""")

wh_context = run_query_cached(session, """
    SELECT WAREHOUSE_NAME, 
           TO_CHAR(DATE_TRUNC('day', START_TIME), 'YYYY-MM-DD') AS DAY,
           ROUND(SUM(CREDITS_USED),2) AS DAILY_CREDITS
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
    WHERE START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
    GROUP BY 1,2 ORDER BY 1,2
""")
```

Then include all this in the prompt for Cortex to reason over.

---

## Feedback 2: Execution Trace / Agent Activity Log

**Current state:** When "Run Detection" or "Apply Fixes" runs, the user just sees a spinner then a rerun. No visibility into what happened.

**Enhancement:** Create an `AGENT_EXECUTION_LOG` table and update procedures to log each step. Show this as a collapsible "Agent Activity" panel in the Operations page.

**New table:**
```sql
CREATE TABLE IF NOT EXISTS FINOPS_GUARDIAN.PUBLIC.AGENT_EXECUTION_LOG (
    EXECUTION_ID NUMBER AUTOINCREMENT PRIMARY KEY,
    SESSION_ID VARCHAR(100) DEFAULT CURRENT_SESSION(),
    EXECUTED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    SKILL_NAME VARCHAR(100),       -- e.g. 'cost-anomaly-detector', 'remediation-applier'
    STEP_NUMBER NUMBER,
    STEP_DESCRIPTION VARCHAR(1000),
    RESULT_SUMMARY VARCHAR(2000),
    STATUS VARCHAR(20) DEFAULT 'COMPLETED'
);
```

**Procedure updates:** Each procedure inserts step-by-step logs (e.g., "Scanning WAREHOUSE_METERING_TEST for idle compute...", "Found 3 new anomalies", "Classifying severity...", "Inserting into USAGE_ANOMALIES...").

**UI:** After running detection/fixes, show the execution trace:
```
🔍 cost-anomaly-detector
  Step 1: Scanning warehouse metering data... ✓
  Step 2: Found 3 idle compute periods ✓
  Step 3: Classifying severity (1 HIGH, 2 MEDIUM) ✓
  Step 4: Logged to USAGE_ANOMALIES ✓
  
🔧 remediation-applier  
  Step 1: Processing 3 open anomalies... ✓
  Step 2: Auto-applied fix for MEDIUM: ALTER WAREHOUSE DEV_WH SET AUTO_SUSPEND=60 ✓
  Step 3: Routing HIGH severity to approval queue ✓
  Step 4: Sending email notification ✓
```

---

## Feedback 3: Email Approval via Secure Webhook

**Current state:** Email notifications contain a link to open the Streamlit dashboard. Users must navigate to the Approvals tab to approve.

**Enhancement:** Add approve/reject links directly in the email that call a stored procedure with a signed token.

**Approach (SiS-compatible):**
Since SiS can't host HTTP endpoints, we'll use a **token-based approval** approach:
1. When generating approval emails, create a unique `APPROVAL_TOKEN` (UUID) stored in a new `APPROVAL_TOKENS` table
2. Email contains a link to the Streamlit app with `?action=approve&token=XXX`
3. On app load, check for query params — if token is valid, auto-approve

**New table:**
```sql
CREATE TABLE IF NOT EXISTS FINOPS_GUARDIAN.PUBLIC.APPROVAL_TOKENS (
    TOKEN_ID VARCHAR(100) PRIMARY KEY,
    ANOMALY_ID NUMBER,
    ACTION VARCHAR(10),  -- 'APPROVE' or 'REJECT'
    CREATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    EXPIRES_AT TIMESTAMP_LTZ,
    USED BOOLEAN DEFAULT FALSE
);
```

**Updated email body:** Include two buttons — "Approve" and "Reject" — each linking to the SiS app URL with the token.

**App startup code:** Check `st.experimental_get_query_params()` for token, validate, and auto-execute approval.

---

## Feedback 4: Expanded Remediation Actions

**Current state:** Only two fix types:
- IDLE_COMPUTE → `ALTER WAREHOUSE ... SET AUTO_SUSPEND = 60`
- COST_SPIKE → `ALTER WAREHOUSE ... SET STATEMENT_TIMEOUT_IN_SECONDS = 3600`

**Enhancement:** Add 3 new anomaly types and remediation actions:

| Anomaly Type | Detection | Remediation |
|---|---|---|
| `OVERSIZED_WAREHOUSE` | Warehouse avg query load < 20% capacity | `ALTER WAREHOUSE ... SET WAREHOUSE_SIZE = 'X-SMALL'` (downsize) |
| `LONG_RUNNING_QUERY` | Queries running > 1 hour | `SELECT SYSTEM$CANCEL_QUERY('query_id')` or flag |
| `IDLE_WAREHOUSE_RUNNING` | Warehouse STARTED with 0 queries for > 10 min | `ALTER WAREHOUSE ... SUSPEND` |

**New procedures:**
- `DETECT_OVERSIZED_WAREHOUSE()` — checks warehouse utilization
- `DETECT_LONG_RUNNING_QUERIES()` — finds queries exceeding thresholds

**Updated APPLY_FIXES():** Add CASE branches for the 3 new anomaly types.

---

## Implementation Order

1. **Task 1:** Create `AGENT_EXECUTION_LOG` and `APPROVAL_TOKENS` tables
2. **Task 2:** Create new detection procedures (`DETECT_OVERSIZED_WAREHOUSE`, `DETECT_LONG_RUNNING_QUERIES`)
3. **Task 3:** Update `APPLY_FIXES()` with expanded remediations and execution logging
4. **Task 4:** Update `DETECT_IDLE_COMPUTE_DEMO()` and `DETECT_COST_SPIKE_DEMO()` with execution logging
5. **Task 5:** Enhance AI chat with richer context and reasoning
6. **Task 6:** Add execution trace panel to Operations UI
7. **Task 7:** Implement token-based email approval flow
8. **Task 8:** Update sidebar with new detection buttons, deploy & push

---

## Constraints & Notes

- **SiS limitations:** No external HTTP endpoints, so email approval uses token-in-URL approach with `st.experimental_get_query_params()`
- **ACCOUNT_USAGE access:** Some queries may fail if the role lacks access — wrapped in try/except with graceful fallback
- **Backwards compatible:** Existing data in USAGE_ANOMALIES and AUDIT_LOG remains valid
- **Credit rate:** All dollar calculations use the existing `CREDIT_RATE = 3.00` variable
