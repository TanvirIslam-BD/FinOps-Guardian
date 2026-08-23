# FinOps Guardian

AI-powered Snowflake warehouse cost monitoring and anomaly detection agent with automated remediation, human-in-the-loop approval, natural language alerts, and a full audit trail.

## Features

### Executive Summary Dashboard

- **Real-time KPI cards** -- Anomalies detected, credits wasted, dollars saved, open issues, CO2 avoided
- **Savings Trend** -- 7-day line chart showing cumulative dollar savings over time
- **Anomalies by Warehouse** -- Bar chart grouping cost spikes and idle compute by warehouse
- **Warehouse Health Scores** -- Live health scoring (0-100) for each warehouse with status badges
- **Environmental Impact** -- Energy saved, CO2 avoided, equivalent trees metrics

### Detection Engine

Each detector is a CoCo CLI skill (`.snowflake/cortex/skills/`) backed by a stored procedure.

| Anomaly Type | Skill | Detection Logic |
|---|---|---|
| **Idle Compute** | `cost-anomaly-detector` | Warehouse running (cloud services > 0) but no query execution (compute = 0) |
| **Cost Spike** | `cost-spike-detector` | Hourly credits exceed 2.5x the rolling 3-hour average |
| **Oversized Warehouse** | `warehouse-optimizer` | Peak hourly draw below 40% of provisioned size capacity |
| **Long-Running Query** | `query-watchdog` | Query exceeds the runtime budget (default 600s), attributed to user and role |

### Remediation Toolkit

The remediation engine picks an action per anomaly from `REMEDIATION_ACTIONS`, renders the
template against the warehouse (and a parameter such as a target size or query ID), then either
applies it or queues it for a human.

| Action | Applies to | Risk | Gate |
|---|---|---|---|
| `SET_AUTO_SUSPEND` | Idle compute | LOW | automatic |
| `SUSPEND_WAREHOUSE` | Idle compute | MEDIUM | automatic |
| `ENABLE_AUTO_RESUME` | Idle compute | LOW | automatic |
| `SET_STATEMENT_TIMEOUT` | Cost spike | LOW | automatic |
| `SET_RESOURCE_MONITOR` | Cost spike | HIGH | approval |
| `SCALE_DOWN_WAREHOUSE` | Oversized warehouse | HIGH | approval |
| `SET_MAX_CLUSTER_COUNT` | Oversized warehouse | MEDIUM | approval |
| `CANCEL_QUERY` | Long-running query | HIGH | approval |
| `FLAG_QUERY_FOR_REVIEW` | Long-running query | LOW | automatic |

- **LOW/MEDIUM severity with a low-risk action** -- applied by the agent immediately
- **HIGH/CRITICAL severity, or any action marked `REQUIRES_APPROVAL`** -- queued as
  `PENDING_APPROVAL` with the exact rendered SQL attached
- **Approvers can override the action** -- the Approvals tab offers every toolkit action valid
  for that anomaly type, with a live SQL preview
- **`DRY_RUN` guard** -- `AGENT_CONFIG.DRY_RUN` defaults to `TRUE`, so a fresh install records
  what it would run and changes nothing. Set it to `FALSE` to let the agent actually
  `ALTER WAREHOUSE`. Audit rows are marked `SIMULATED` while it is on.

### Agent Execution Trace

Every skill writes one row per reasoning step to `AGENT_EXECUTION_LOG` as it runs. Because DML
inside a Snowflake procedure autocommits, a run started by a scheduled task is visible in the
Operations tab while it is still executing -- steps show as RUNNING behind a live badge, then
resolve to COMPLETED with their duration. Runs triggered from Quick Actions are pinned to the
top of the trace so you see exactly what the agent just did.

### Smart Alerts -- Natural Language (AI-Powered)

- **Plain English rules** -- Create monitoring alerts using natural language (e.g., "Notify me if any warehouse spends more than $50 per day")
- **Cortex AI parsing** -- Rules are parsed by Snowflake Cortex (`llama3.1-70b`) into structured JSON with metric, threshold, warehouse, and condition
- **Visual rule display** -- Parsed alert rules shown as colored tags for metric, threshold, and target warehouse
- **Active alerts management** -- View, activate, and delete alerts from the UI
- **Persistent storage** -- Alerts stored in `SMART_ALERTS` table with trigger tracking

### AI-Powered Insights (Cortex AI)

- **Skill-grounded chat** -- Ask FinOps Guardian is wired to the output of every skill, not just
  the anomaly table. Each question is answered against the detected anomalies, the longest-running
  queries with their owning user and role, cost attribution by user and role, hourly warehouse
  spend, the remediation actions the agent has taken, and the recent execution trace.
- **Explanations, not table dumps** -- the model is instructed to name specific warehouses, users,
  roles and query IDs, quote real figures, say which skill produced each finding, and close with
  one concrete next action from the toolkit.
- **Charts alongside the prose** -- spend-by-warehouse and spend-by-user render directly under the
  answer, built from the same rows the model saw.
- **Evidence panel** -- an expander shows every table passed to Cortex, so any number in the answer
  can be traced back to its source.
- **Cost Attribution** -- credit consumption broken down by user and role
- **Week-over-Week Analysis** -- Per-warehouse credit usage with % change indicators

### Operations Center

- **Live agent execution trace** -- Step-by-step skill reasoning, streaming while runs are in flight
- **Remediation toolkit browser** -- Every action the agent can take, with its risk level, approval
  gate, owning skill and SQL template
- **Real-time warehouse status** -- Live view of all warehouses (RUNNING/SUSPENDED, size, auto-suspend, queued queries)
- **Auto-fix history** -- Timeline of all automated remediation actions taken

### Human-in-the-Loop Approvals

- **Pending recommendations** -- HIGH/CRITICAL fixes and high-risk actions queued for manual review
- **Exact SQL shown** -- the approver sees the rendered statement, not a template
- **Action override** -- pick a different toolkit action before approving, with a SQL preview
- **One-click approve or reject** -- both paths execute server-side and log to the audit trail
- **Recently approved** -- history of past decisions, showing whether each came through the
  dashboard or an email link

### Direct Email Approvals

HIGH/CRITICAL remediations can be approved or rejected straight from the notification email --
no need to open the dashboard first and hunt for the anomaly.

- `SEND_APPROVAL_EMAIL` mints two single-use tokens (approve, reject) and emails an HTML summary
  with the warehouse, credits at risk, the proposed SQL, and two buttons.
- Links carry `?token=<uuid>&action=approve|reject` ahead of the Snowsight fragment, so the
  parameters survive the redirect.
- Redeeming a link calls `CONSUME_APPROVAL_TOKEN`, which validates format, expiry, single use and
  action match **server side**. The token is passed as a bind parameter and never concatenated
  into SQL.
- Opening the link authenticates the reviewer against Snowflake, so their real identity -- not the
  token -- is what lands in `AUDIT_LOG.APPROVED_BY`, with `APPROVAL_CHANNEL = 'EMAIL'`.
- Tokens expire after `AGENT_CONFIG.TOKEN_TTL_HOURS` (default 48) and burn on first use.
- The `HIGH_SEVERITY_ALERT` alert dispatches these emails every 15 minutes for anything still
  waiting. The Approvals tab can also generate and display the links on demand, which is how you
  demo the flow without a mailbox.

### Policy Compliance

- **Auto-suspend checks** -- Validates all warehouses have appropriate auto-suspend timeouts
- **Warehouse sizing** -- Flags oversized warehouses that could be downsized
- **Compliance scoring** -- Overall pass rate with severity-tagged findings
- **Policy recommendations** -- Actionable SQL to remediate non-compliant configurations

### Notifications

- **In-app notification center** -- All system events displayed with severity badges
- **Read/unread tracking** -- Mark individual or all notifications as read
- **Severity filtering** -- INFO, WARNING, ERROR, CRITICAL with color-coded badges

### Audit Trail

- **Full action history** -- Every detection, recommendation, approval, and auto-fix logged
- **Filterable log** -- Filter by warehouse, status, and action type
- **Statistics dashboard** -- Total entries, auto actions, manual actions, pending count

### Scheduled Monitoring

- **Hourly detection chain** -- Four detection skills run in sequence every hour
  (`TASK_DETECT_IDLE` -> `SPIKE` -> `OVERSIZED` -> `LONG_QUERIES`)
- **Automated remediation** -- `TASK_APPLY_FIXES` runs after detection, then alert evaluation and
  the daily savings snapshot
- **Approval emails** -- `HIGH_SEVERITY_ALERT` fires every 15 minutes and emails one-click
  approve/reject links for anything still awaiting a human
- **Created suspended** -- nothing runs, and nothing bills, until you resume the tasks

### Performance Optimizations

- **Query caching** -- Read-only dashboard queries cached with 120s TTL for instant tab switching,
  invalidated immediately after any write so an action never looks like it failed
- **Single-click navigation** -- Immediate tab switching with `experimental_rerun()`
- **Smooth transitions** -- CSS animations for content loading (fadeIn)
- **Light theme enforcement** -- Forced light theme via `config.toml` for consistent rendering

### Demo Controls

- **One-click reset** -- Wipe and re-seed all data for a clean live demo
- **Quick Actions** -- Run any single skill on demand (Idle Scan, Spikes, Oversized, Long Queries,
  Apply Fixes); each jumps to Operations with its execution trace pinned open
- **Scan profiles** -- Configurable scan presets

## Architecture

```
+-----------------------------------------------------------+
|                    Streamlit Dashboard                     |
|  Executive Summary | Operations | Approvals | Intelligence |
|  Compliance | Notifications | Audit Trail                  |
|                                                            |
|  live skill trace  .  grounded chat  .  email approvals    |
+-----------------------------+------------------------------+
                              |
+-----------------------------v-----------------------------+
|              Cortex AI (llama3.1-70b)                      |
|  NL alert parsing | Chat grounded in skill output          |
+-----------------------------+------------------------------+
                              |
+-----------------------------v-----------------------------+
|          CoCo CLI Agent Skills (.snowflake/cortex/skills)  |
|  cost-anomaly-detector | cost-spike-detector               |
|  warehouse-optimizer   | query-watchdog                    |
|  remediation-engine    | remediation-approver              |
|  alert-evaluator                                           |
|            every step -> AGENT_EXECUTION_LOG               |
+-----------------------------+------------------------------+
                              |
+-----------------------------v-----------------------------+
|              Snowflake Tasks (hourly chain)                |
|  DETECT_IDLE -> SPIKE -> OVERSIZED -> LONG_QUERIES         |
|      -> APPLY_FIXES -> EVALUATE_ALERTS -> SNAPSHOT         |
|  HIGH_SEVERITY_ALERT (15 min) -> approval emails           |
+-----------------------------+------------------------------+
                              |
+-----------------------------v-----------------------------+
|              Stored Procedures                             |
|  DETECT_* | APPLY_FIXES | EXECUTE_REMEDIATION              |
|  APPROVE_FIX | REJECT_FIX | CONSUME_APPROVAL_TOKEN         |
|  SEND_APPROVAL_EMAIL | EVALUATE_SMART_ALERTS | SNAPSHOT     |
+-----------------------------+------------------------------+
                              |
+-----------------------------v-----------------------------+
|              Snowflake Tables                              |
|  USAGE_ANOMALIES | AUDIT_LOG | SAVINGS_HISTORY             |
|  AGENT_SKILLS | AGENT_EXECUTION_LOG | REMEDIATION_ACTIONS  |
|  APPROVAL_TOKENS | SMART_ALERTS | NOTIFICATIONS            |
|  AGENT_CONFIG | *_TEST (demo data)                         |
+-----------------------------+------------------------------+
                              |
+-----------------------------v-----------------------------+
|              Snowflake Platform                            |
|  ACCOUNT_USAGE | Cortex AI | Email Notifications | Alerts  |
+-----------------------------------------------------------+
```

## Live Demo

**[Open the live app](https://app.snowflake.com/streamlit/ap-southeast-7.aws/em69097/#/apps/FINOPS_GUARDIAN.PUBLIC.FINOPS_GUARDIAN_APP)** (requires access to the `em69097` Snowflake account)

The app is deployed to Streamlit-in-Snowflake with a polished sidebar UI and instant navigation.

**Demo flow for judges:**

1. Click **Reset Demo** -- re-runs all four detection skills and the remediation engine
2. Observe **KPI cards** -- anomalies, credits wasted, dollars saved, CO2 avoided
3. See **Savings Trend** and **Warehouse Health Scores**
4. Go to **Operations** -- watch the **Agent Execution Trace**: the run you just triggered is
   pinned at the top with its steps, results and timings, and the **Remediation Toolkit** below
   lists all nine actions the agent can take
5. Trigger a single skill from **Quick Actions** (Idle Scan, Spikes, Oversized, Long Queries)
   and watch its trace appear
6. Go to **Approvals** -- pick a pending item, switch the **remediation action** in the dropdown
   to see the SQL preview change, then click **Email approval links** to mint the approve/reject
   links and open one straight from the page
7. Go to **Intelligence** -- ask *"which user caused the cost increase?"* and read the prose
   answer naming the query, user and role, with the skills it relied on shown as chips, charts
   underneath, and the **Evidence** expander showing exactly what Cortex was given
8. Create a **Smart Alert** in plain English and watch Cortex parse it into a structured rule
9. Go to **Compliance** -- policy checks and remediation SQL
10. Show **Audit Trail** -- every action, with the approval channel (UI, EMAIL or AUTO) recorded

## Project Structure

```
FinOpsGuardian/
|-- streamlit_app.py       # Dashboard (deployed to Streamlit-in-Snowflake)
|-- setup.sql              # All SQL to recreate the backend, top to bottom
|-- snowflake.yml          # SiS deployment manifest
|-- pyproject.toml         # Python dependencies
|-- README.md              # This file
|-- .streamlit/
|   `-- config.toml        # Light theme with purple accent
`-- .snowflake/cortex/
    |-- skills/            # CoCo CLI agent skills (mirrored in AGENT_SKILLS)
    |   |-- cost-anomaly-detector.md
    |   |-- cost-spike-detector.md
    |   |-- warehouse-optimizer.md
    |   |-- query-watchdog.md
    |   |-- remediation-engine.md
    |   |-- remediation-approver.md
    |   `-- alert-evaluator.md
    `-- plans/             # Implementation plans
```

Each skill file documents its steps and reasoning; the `AGENT_SKILLS` table carries the same
metadata so the dashboard and the Cortex chat can reference skills by name at runtime.

## Setup

### Prerequisites

- Snowflake account with `ACCOUNTADMIN` role
- Cortex AI enabled (for LLM features -- `llama3.1-70b`)
- Warehouse `COMPUTE_WH` available

### Deploy

1. Upload the app to the stage (the stage is created by `setup.sql`, so run step 2 first if this
   is a brand-new account):
   ```sql
   PUT 'file://./streamlit_app.py' @FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
   PUT 'file://./.streamlit/config.toml' @FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE/.streamlit/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
   ```
2. Run `setup.sql` top to bottom in a Snowflake worksheet. It creates every table, procedure,
   task and alert, seeds demo data, and runs the full pipeline once.
3. The app appears under **Projects > Streamlit > FinOps Guardian** in Snowsight.

`setup.sql` is idempotent for schema objects (`CREATE TABLE IF NOT EXISTS` / `CREATE OR REPLACE
PROCEDURE`) but re-seeds the demo tables and truncates transactional data at the end. Re-running
it resets the demo; it does not migrate an existing install.

### Configuration

All runtime switches live in the `AGENT_CONFIG` table:

| Key | Default | What it does |
|---|---|---|
| `DRY_RUN` | `TRUE` | When TRUE the agent records remediation SQL but never executes it. Audit rows read `SIMULATED`. |
| `APP_URL` | Snowsight app URL | Base URL used to build the approve/reject links in email. |
| `ALERT_RECIPIENT` | *(empty)* | Verified Snowflake user email that receives approval requests. Empty disables delivery. |
| `CREDIT_RATE` | `3.00` | USD per credit, used for every dollar figure. |
| `TOKEN_TTL_HOURS` | `48` | Lifetime of an emailed approve/reject link. |

```sql
-- Let the agent actually alter warehouses
UPDATE FINOPS_GUARDIAN.PUBLIC.AGENT_CONFIG SET CONFIG_VALUE = 'FALSE' WHERE CONFIG_KEY = 'DRY_RUN';

-- Turn on email approvals
UPDATE FINOPS_GUARDIAN.PUBLIC.AGENT_CONFIG SET CONFIG_VALUE = 'you@example.com' WHERE CONFIG_KEY = 'ALERT_RECIPIENT';
```

`DRY_RUN` defaults to TRUE on purpose: installing this project should never change a warehouse
until you say so. The remediation path, audit trail and approval flow all work identically in
either mode -- only the `EXECUTE IMMEDIATE` is skipped.

### Enable Scheduled Monitoring

Tasks are created suspended. Resume them child-first, root last:

```sql
ALTER TASK FINOPS_GUARDIAN.PUBLIC.TASK_SNAPSHOT_SAVINGS    RESUME;
ALTER TASK FINOPS_GUARDIAN.PUBLIC.TASK_EVALUATE_ALERTS     RESUME;
ALTER TASK FINOPS_GUARDIAN.PUBLIC.TASK_APPLY_FIXES         RESUME;
ALTER TASK FINOPS_GUARDIAN.PUBLIC.TASK_DETECT_LONG_QUERIES RESUME;
ALTER TASK FINOPS_GUARDIAN.PUBLIC.TASK_DETECT_OVERSIZED    RESUME;
ALTER TASK FINOPS_GUARDIAN.PUBLIC.TASK_DETECT_SPIKE        RESUME;
ALTER TASK FINOPS_GUARDIAN.PUBLIC.TASK_DETECT_IDLE         RESUME;
ALTER ALERT FINOPS_GUARDIAN.PUBLIC.HIGH_SEVERITY_ALERT     RESUME;
```

## Snowflake Objects

| Object | Type | Purpose |
|---|---|---|
| `FINOPS_GUARDIAN` | Database | Project home |
| `AGENT_CONFIG` | Table | Runtime switches (DRY_RUN, credit rate, email recipient, token TTL) |
| `USAGE_ANOMALIES` | Table | Detected anomalies with severity, recommended action and status |
| `AUDIT_LOG` | Table | Full action history, including the approval channel for each decision |
| `SAVINGS_HISTORY` | Table | Daily savings snapshots for the trend chart |
| `AGENT_SKILLS` | Table | Skill registry mirroring `.snowflake/cortex/skills/` |
| `AGENT_EXECUTION_LOG` | Table | Per-step skill trace, written live during a run |
| `REMEDIATION_ACTIONS` | Table | The remediation toolkit: SQL templates, risk, approval gate |
| `APPROVAL_TOKENS` | Table | Single-use expiring tokens behind the email approve/reject links |
| `SMART_ALERTS` | Table | Natural language alert rules parsed by Cortex |
| `NOTIFICATIONS` | Table | In-app notification events |
| `WAREHOUSE_METERING_TEST` | Table | Synthetic metering data (generated relative to today) |
| `WAREHOUSE_CONFIG_TEST` | Table | Synthetic warehouse sizes for the optimizer skill |
| `QUERY_HISTORY_TEST` | Table | Synthetic query history for the watchdog skill |
| `LOG_AGENT_STEP` | Procedure | Writes one trace step |
| `NOTIFY` | Procedure | Raises an in-app notification |
| `DETECT_IDLE_COMPUTE` | Procedure | Idle scan against `ACCOUNT_USAGE` |
| `DETECT_IDLE_COMPUTE_DEMO` | Procedure | Idle scan against demo data |
| `DETECT_COST_SPIKE_DEMO` | Procedure | Rolling-average spike detection |
| `DETECT_OVERSIZED_WAREHOUSE` | Procedure | Peak-vs-capacity utilisation check |
| `DETECT_LONG_RUNNING_QUERIES` | Procedure | Runtime-budget check with user/role attribution |
| `APPLY_FIXES` | Procedure | Matches anomalies to toolkit actions, applies or queues |
| `EXECUTE_REMEDIATION` | Procedure | Renders and runs one action, honouring `DRY_RUN` |
| `APPROVE_FIX` | Procedure | Approve (2-arg and 4-arg forms), with optional action override |
| `REJECT_FIX` | Procedure | Reject a proposed remediation |
| `GENERATE_APPROVAL_TOKEN` | Procedure | Mints a single-use approval token |
| `CONSUME_APPROVAL_TOKEN` | Procedure | Validates and redeems a token, server side |
| `SEND_APPROVAL_EMAIL` | Procedure | Builds the links and emails them; returns them as JSON |
| `SEND_PENDING_APPROVAL_EMAILS` | Procedure | Bulk dispatch for the alert |
| `EVALUATE_SMART_ALERTS` | Procedure | Evaluates parsed NL rules against metering data |
| `SNAPSHOT_SAVINGS` | Procedure | Daily savings rollup |
| `TASK_DETECT_IDLE` | Task | Hourly root of the detection chain |
| `TASK_DETECT_SPIKE` | Task | Spike scan |
| `TASK_DETECT_OVERSIZED` | Task | Oversized-warehouse scan |
| `TASK_DETECT_LONG_QUERIES` | Task | Long-running query scan |
| `TASK_APPLY_FIXES` | Task | Remediation pass after detection |
| `TASK_EVALUATE_ALERTS` | Task | Smart alert evaluation |
| `TASK_SNAPSHOT_SAVINGS` | Task | Savings snapshot |
| `HIGH_SEVERITY_ALERT` | Alert | Emails approval links every 15 minutes |
| `FINOPS_ALERTS` | Integration | Email notification channel |

## Tech Stack

- **Snowflake** -- Stored procedures, tasks, alerts, email notification integration,
  Streamlit-in-Snowflake
- **Cortex AI (`llama3.1-70b`)** -- NL alert parsing and skill-grounded chat reasoning
- **CoCo CLI skills** -- Seven agent skills in `.snowflake/cortex/skills/`, mirrored in the
  `AGENT_SKILLS` table and traced per step in `AGENT_EXECUTION_LOG`
- **Streamlit** -- Dashboard with cached reads, bound-parameter writes and a live skill trace
- **SQL** -- All detection and remediation logic runs natively in Snowflake (zero external compute)
- **Altair** -- Charts rendered alongside the AI answers from the same evidence

## Security Notes

- Every value that reaches SQL is passed as a **bind parameter**, including Cortex prompts,
  LLM-parsed alert fields and approval tokens. Nothing user- or model-supplied is concatenated
  into a statement.
- The alert parser's output is **clamped to a fixed vocabulary** of metrics and conditions before
  it is stored, so a prompt-injected metric name cannot become SQL.
- Approval tokens are validated **server side** in `CONSUME_APPROVAL_TOKEN` -- format, expiry,
  single use and action match -- and the redeemer's Snowflake identity, not the token, is what is
  recorded as the approver.
- Database values rendered into HTML are escaped with `html.escape`.
- `DRY_RUN` defaults to `TRUE`, so the agent cannot alter a warehouse until explicitly enabled.

## License

MIT
