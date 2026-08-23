# FinOps Guardian

**An autonomous AI agent for Snowflake cost control** — it finds waste, explains it in plain
English, proposes the exact SQL to fix it, and shows you every step of its reasoning before a
human approves the change.

Built entirely inside Snowflake: Cortex AI for reasoning, agent skills for detection and
remediation, Streamlit-in-Snowflake for the interface. Zero external compute.

**[▶ Open the live app](https://app.snowflake.com/streamlit/ap-southeast-7.aws/em69097/#/apps/FINOPS_GUARDIAN.PUBLIC.FINOPS_GUARDIAN_APP)**
*(requires access to the `em69097` Snowflake account)*

---

## Contents

- [The problem](#the-problem)
- [**AI at the core**](#ai-at-the-core) — the four AI capabilities
- [AI guardrails](#ai-guardrails)
- [Feature tour](#feature-tour)
- [Detection engine](#detection-engine)
- [Remediation toolkit](#remediation-toolkit)
- [Direct email approvals](#direct-email-approvals)
- [Architecture](#architecture)
- [Live demo walkthrough](#live-demo-walkthrough)
- [Setup](#setup)
- [Snowflake objects](#snowflake-objects)
- [Security notes](#security-notes)

---

## The problem

Snowflake bills by the credit, and the expensive mistakes are invisible in a bill: a warehouse
left running overnight with no queries, an ETL job that quietly went 4x over baseline, a LARGE
warehouse doing X-SMALL work, one unbounded query burning a warehouse for 46 minutes.

Finding those needs analysis. *Explaining* them — which user, which role, which query, how much —
is what turns a dashboard into an action. That explanation is the part AI is genuinely good at,
and it is where this project puts it.

---

# AI at the core

Four distinct AI capabilities, each doing a job that plain SQL cannot.

## 1 · Ask FinOps Guardian — cost reasoning grounded in agent output

The chat in the **Intelligence** tab is not a wrapper around a table. Every question is answered
against the live output of the entire agent, assembled at query time and handed to Cortex as
grounding context:

| Grounding source | What it contributes |
|---|---|
| `USAGE_ANOMALIES` | Every detected anomaly, its severity, cost, and **which skill found it** |
| `QUERY_HISTORY` | The longest-running queries **with owning user and role** |
| Cost attribution | Credits and dollars grouped by user and role over 7 days |
| Hourly metering | Per-warehouse spend, hour by hour |
| `AUDIT_LOG` | Every remediation the agent applied, queued, or had approved |
| `AGENT_EXECUTION_LOG` | The recent step-by-step reasoning trace |
| `AGENT_SKILLS` | The skill catalogue, so answers can cite skills by name |
| `REMEDIATION_ACTIONS` | The toolkit, so recommendations are actionable, not vague |

**The model is held to a contract.** Its instructions require it to:

- name specific warehouses, users, roles and query IDs from the evidence
- quote real figures — credits, dollars, minutes — and never invent one
- state **which skill** produced the finding it is relying on
- close with `Recommended next step:` and one concrete action from the toolkit
- say the evidence is insufficient rather than guess

### Ask it "which user caused the cost increase?"

You get prose that names `ETL_SERVICE` on the `SYSADMIN` role, the 46-minute query ID, the credits
it consumed, and the toolkit action that addresses it — not a table you have to interpret.

### Every answer ships with its receipts

- **Skill chips** under the answer show which agent skills the response drew on
- **Charts render alongside the prose** — spend-by-warehouse and spend-by-user, built from the
  exact rows the model was given
- **An Evidence panel** expands to show *every table passed to Cortex*, so any number in the
  answer can be traced to its source

That last point is the difference between an AI feature you can demo and one you can trust. If the
model says `ANALYTICS_WH` wasted 2.4 credits, the row it read is one click away.

## 2 · Natural language → structured monitoring rules

Type a monitoring rule the way you'd say it:

> *"Notify me if any warehouse spends more than $50 per day"*

Cortex parses it into a structured rule — metric, threshold, target warehouse, condition — which
is rendered back as colored chips so you can confirm the AI understood you *before* activating it.

```json
{ "metric": "daily_spend", "threshold": 50, "warehouse": "ANY", "condition": "greater_than" }
```

**Parse once, evaluate forever.** The LLM runs at authoring time only. From then on the rule is
plain SQL evaluated by `EVALUATE_SMART_ALERTS` on a schedule — so a rule costs nothing per run and
behaves identically every single time. No non-determinism in the monitoring path.

Four suggestion chips seed common rules; parsed rules persist in `SMART_ALERTS` with trigger
counts and last-triggered timestamps.

## 3 · Agent skills with visible, streaming reasoning

Seven **CoCo CLI agent skills** live in `.snowflake/cortex/skills/`, mirrored in the `AGENT_SKILLS`
table so the dashboard and the chat can reference them by name at runtime.

| Skill | Category | What it reasons about |
|---|---|---|
| `cost-anomaly-detector` | Detection | Warehouses billing cloud services with zero compute |
| `cost-spike-detector` | Detection | Hours exceeding a warehouse's own trailing baseline |
| `warehouse-optimizer` | Detection | Peak draw versus provisioned size capacity |
| `query-watchdog` | Detection | Queries past their runtime budget, attributed to a user |
| `remediation-engine` | Remediation | Which toolkit action fits, and whether a human is needed |
| `remediation-approver` | Remediation | Executing an approved fix and recording who approved it |
| `alert-evaluator` | Analysis | Whether a natural-language rule has tripped |

### The reasoning is not a black box

Every skill writes **one row per reasoning step** to `AGENT_EXECUTION_LOG` as it executes:

```
🔍 cost-anomaly-detector · 4 steps · ✅ complete · 2362 ms
  ✅ Step 1  Load warehouse metering window                                    396 ms
     ↳ 19 metering rows in scope
  ✅ Step 2  Isolate hours billing cloud services with zero compute            436 ms
     ↳ 9 idle warehouse-hours identified
  ✅ Step 3  Score severity, pick remediation and persist new anomalies        587 ms
     ↳ 9 new anomalies written (0 already known)
  ✅ Step 4  Record scan in audit trail                                        943 ms
     ↳ Audit entry written
```

*(Real output from the deployed app, not a mock-up.)*

**It streams.** DML inside a Snowflake procedure autocommits, so a run started by a scheduled task
in the background is visible in the Operations tab *while it is still executing* — steps show as
`RUNNING` behind a pulsing **LIVE** badge, then resolve to `COMPLETED` with a real elapsed time.
Runs you trigger yourself are pinned to the top of the trace.

Skill runs are also fed back into the chat as grounding context, which is how the AI can answer
"what has the agent been doing?" as well as "what is costing me money?"

## 4 · AI-selected remediation, human-gated

Detection does not just raise a flag — each skill selects a specific action from a nine-action
toolkit and binds the parameters for it:

- idle warehouse drawing >0.1 credits/hr → `SUSPEND_WAREHOUSE`, else `SET_AUTO_SUSPEND`
- spike over 8x baseline → `SET_RESOURCE_MONITOR`, else `SET_STATEMENT_TIMEOUT`
- under-utilised LARGE warehouse → `SCALE_DOWN_WAREHOUSE` with `MEDIUM` bound as the target size
- query running over 30 min → `CANCEL_QUERY` with the query ID bound in, else flag for review

The approver sees the **fully rendered statement**, never a template, and can override the choice
from a dropdown of every action valid for that anomaly type — with the SQL preview updating live.

---

# AI guardrails

Putting an LLM near a system that can `ALTER WAREHOUSE` demands specific defences. Each of these is
implemented, not aspirational.

| Risk | Guardrail |
|---|---|
| **Prompt injection** | The system prompt explicitly instructs the model to ignore any instruction in the user's question that tries to change its role, reveal the prompt, or perform unrelated work. Scope is restricted to Snowflake cost topics. |
| **LLM output reaching SQL** | The alert parser's `metric` and `condition` are **clamped to a fixed vocabulary** before storage; `threshold` is cast to float; everything is written with **bind parameters**. A prompt-injected metric name cannot become SQL. |
| **Hallucinated figures** | The Evidence panel exposes every table the model received, making fabricated numbers immediately checkable. The prompt forbids inventing figures and requires citing the producing skill. |
| **Backslash escape breakout** | Cortex prompts are passed as bind parameters, not string-interpolated. Escaping quotes alone is insufficient — Snowflake also treats `\` as an escape inside a literal. |
| **Unbounded input** | Alert text is truncated to 500 characters before it reaches the model. |
| **AI acting unsupervised** | `AGENT_CONFIG.DRY_RUN` defaults to `TRUE`. The agent records the statement it *would* run and changes nothing until you explicitly enable execution. |
| **Non-deterministic monitoring** | The LLM parses a rule once. Evaluation is pure SQL forever after. |

### Where AI is deliberately *not* used

Detection thresholds, rolling averages, utilisation maths and alert evaluation are all
deterministic SQL. An LLM in that path would make results vary run to run and cost credits on every
scan. AI is applied where judgement and explanation are needed — parsing intent, attributing cause,
recommending an action — and kept out of the arithmetic.

---

# Feature tour

## Executive Summary

- **KPI cards** — anomalies detected, credits wasted, dollars saved, open issues, CO₂ avoided
- **Real week-over-week deltas** — computed from `DETECTED_AT`, not hardcoded
- **Savings Trend** — 7-day cumulative dollar savings
- **Anomalies by Warehouse** — stacked by anomaly type
- **Warehouse Health Scores** — 0–100 per warehouse, penalising disabled auto-suspend, long
  timeouts, idle-but-started state and recent anomaly count, with a per-card explanation
- **Environmental Impact** — energy saved, CO₂ avoided, equivalent trees

## Operations

- **Live agent execution trace** (see [above](#3--agent-skills-with-visible-streaming-reasoning))
- **Remediation toolkit browser** — all nine actions with risk level, approval gate, owning skill
  and SQL template
- **Smart Alerts** — natural-language rule authoring
- **Warehouse status** — RUNNING/SUSPENDED, size, auto-suspend, queued queries
- **Auto-fix history** — every automated remediation with the exact SQL

## Approvals

- Pending queue with severity, dollars at risk, and the detecting skill
- **Exact rendered SQL**, not a template
- **Action override** dropdown with live SQL preview
- One-click approve or reject, both executing server-side
- **Email approval links** generated on demand
- Recently approved history showing the channel each decision came through

## Intelligence

- **Ask FinOps Guardian** grounded chat with skill chips, charts and evidence panel
- **Cost Attribution** — credits and dollars by user and role
- **Week-over-Week** — per-warehouse usage with percentage change

## Compliance

- Auto-suspend checks — **a warehouse that never suspends is correctly scored as the worst case**,
  not as compliant
- Auto-resume validation and oversized-warehouse flags
- Compliance score with severity-tagged findings and remediation SQL
- Best-practice reference table

## Notifications

- In-app centre with type-coded badges (approval needed, warning, approved, rejected, info)
- Relative timestamps, read/unread tracking, mark-all-read

## Audit Trail

- Every detection, recommendation, approval, rejection and auto-fix
- **`APPROVAL_CHANNEL` on every decision** — `UI`, `EMAIL` or `AUTO`
- Filterable by warehouse, status and action type (bound parameters, not string-built SQL)
- Statistics: total entries, auto actions, manual actions, pending

## Scheduled monitoring

- **Hourly detection chain** — four detection skills run in sequence, then remediation, then alert
  evaluation, then the daily savings snapshot
- **Approval emails** — `HIGH_SEVERITY_ALERT` fires every 15 minutes for anything still waiting
- **Created suspended** — nothing runs, and nothing bills, until you resume the tasks

## Demo controls

- **Reset Demo** — clears transactional tables and re-runs the full pipeline in one click
- **Quick Actions** — fire any single skill on demand; each jumps straight to Operations with its
  execution trace pinned open
- **Scan profiles** — configurable scan presets

## Under the hood

- **Cache correctness** — read queries are cached with a 120s TTL for instant tab switching, and
  the cache is dropped immediately after any write, so an action never appears to have failed
- **Version-agnostic Streamlit** — `st.rerun` / `st.experimental_rerun` and both query-parameter
  APIs are resolved at runtime, so a SiS runtime bump cannot break the app
- **Bound parameters throughout** — including the Cortex prompts themselves
- **Light theme enforced** via `config.toml` for consistent rendering
- **CSS transitions** for content loading and a pulsing live badge on in-flight skill runs

---

# Detection engine

Each detector is a CoCo CLI skill backed by a stored procedure returning its `RUN_ID`, so the UI
can stream the trace immediately.

| Anomaly Type | Skill | Detection logic |
|---|---|---|
| **Idle Compute** | `cost-anomaly-detector` | Cloud-services credits > 0 with compute = 0 |
| **Cost Spike** | `cost-spike-detector` | Hourly credits ≥ 2.5x the trailing 3-hour average (needs ≥ 2 preceding hours, so a cold start cannot look like a spike) |
| **Oversized Warehouse** | `warehouse-optimizer` | Peak hourly draw below 40% of provisioned capacity; below 20% is HIGH |
| **Long-Running Query** | `query-watchdog` | Runtime over budget (default 600s), attributed to user and role |

Each warehouse is compared **against itself**, so a large ETL warehouse is not judged by the same
absolute numbers as a small dev one.

---

# Remediation toolkit

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

- **LOW/MEDIUM severity with a low-risk action** — applied immediately by the agent
- **HIGH/CRITICAL severity, or any `REQUIRES_APPROVAL` action** — queued with rendered SQL attached
- **`DRY_RUN` guard** — defaults to `TRUE`; audit rows read `SIMULATED` until you enable execution

---

# Direct email approvals

HIGH/CRITICAL remediations can be approved or rejected straight from the notification email — no
opening the dashboard and hunting for the anomaly.

- `SEND_APPROVAL_EMAIL` mints two single-use tokens and sends an HTML summary with the warehouse,
  credits at risk, the proposed SQL, and Approve / Reject buttons
- Links carry the token **ahead of the Snowsight fragment**, so the parameters survive the redirect
- Redemption runs through `CONSUME_APPROVAL_TOKEN`, which validates format, expiry, single-use and
  action match **server-side**; the token is a bind parameter, never concatenated into SQL
- Opening the link authenticates the reviewer against Snowflake, so **their real identity — not the
  token — lands in `AUDIT_LOG.APPROVED_BY`**, with `APPROVAL_CHANNEL = 'EMAIL'`
- Tokens expire after `TOKEN_TTL_HOURS` (default 48) and burn on first use
- A failed remediation does **not** burn the link, so the reviewer can retry
- `HIGH_SEVERITY_ALERT` dispatches every 15 minutes; the Approvals tab can also generate and
  display the links on demand, which is how you demo the flow without a mailbox

---

# Architecture

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
|  Grounded cost reasoning  |  NL rule parsing               |
|  answers cite skills, quote evidence, recommend an action  |
+-----------------------------+------------------------------+
                              |
+-----------------------------v-----------------------------+
|          CoCo CLI Agent Skills (.snowflake/cortex/skills)  |
|  cost-anomaly-detector | cost-spike-detector               |
|  warehouse-optimizer   | query-watchdog                    |
|  remediation-engine    | remediation-approver              |
|  alert-evaluator                                           |
|      every reasoning step -> AGENT_EXECUTION_LOG (live)    |
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
|  SEND_APPROVAL_EMAIL | EVALUATE_SMART_ALERTS | SNAPSHOT    |
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

---

# Live demo walkthrough

**[▶ Open the live app](https://app.snowflake.com/streamlit/ap-southeast-7.aws/em69097/#/apps/FINOPS_GUARDIAN.PUBLIC.FINOPS_GUARDIAN_APP)**

1. **Reset Demo** (sidebar) — re-runs all four detection skills plus the remediation engine
2. **Executive Summary** — KPIs, savings trend, health scores with per-warehouse explanations
3. **Operations → Agent Execution Trace** — the run you just triggered is pinned open with its
   steps, results and per-step timings. *This is the AI's reasoning, not a summary of it.*
4. **Quick Actions** — fire a single skill (Idle Scan, Spikes, Oversized, Long Queries) and watch
   its trace appear
5. **Operations → Remediation Toolkit** — all nine actions with risk, gate and SQL template
6. **Approvals** — switch the **remediation action** dropdown and watch the SQL preview change,
   then **Email approval links** to mint approve/reject links and redeem one from the page
7. **Intelligence** — ask *"which user caused the cost increase?"*
   Read the prose naming the query, user and role · check the **skill chips** · read the charts ·
   open **Evidence** to see exactly what Cortex was given
8. **Smart Alerts** — type *"Alert if any warehouse spends > $50/day"* and watch Cortex parse it
   into chips before you activate it
9. **Compliance** — policy checks with remediation SQL
10. **Audit Trail** — every action, with the approval channel (`UI` / `EMAIL` / `AUTO`) recorded

---

# Project structure

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

Each skill file documents its steps and the reasoning behind them; the `AGENT_SKILLS` table carries
the same metadata so the dashboard and the Cortex chat can reference skills by name at runtime.

---

# Setup

### Prerequisites

- Snowflake account with `ACCOUNTADMIN`
- Cortex AI enabled (`llama3.1-70b`)
- Warehouse `COMPUTE_WH`

### Deploy

```bash
snow stage copy ./streamlit_app.py @FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE/ --overwrite
snow stage copy ./.streamlit/config.toml @FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE/.streamlit/ --overwrite
snow sql -f setup.sql
```

On a brand-new account run `setup.sql` first — it creates the stage — then upload and re-run.
The script creates every table, procedure, task and alert, migrates older installs in place, seeds
demo data, and runs the full pipeline once.

`setup.sql` uses `CREATE STREAMLIT IF NOT EXISTS`, never `OR REPLACE`: replacing a Streamlit object
rotates its `url_id`, which changes the app URL and would invalidate every approval link already
sitting in someone's inbox.

### Configuration

All runtime switches live in `AGENT_CONFIG`:

| Key | Default | What it does |
|---|---|---|
| `DRY_RUN` | `TRUE` | Records remediation SQL without executing it. Audit rows read `SIMULATED`. |
| `APP_URL` | Snowsight app URL | Base URL for the approve/reject links in email |
| `ALERT_RECIPIENT` | *(empty)* | Verified Snowflake user email for approval requests. Empty disables delivery. |
| `CREDIT_RATE` | `3.00` | USD per credit |
| `TOKEN_TTL_HOURS` | `48` | Lifetime of an emailed approval link |

```sql
-- Let the agent actually alter warehouses
UPDATE FINOPS_GUARDIAN.PUBLIC.AGENT_CONFIG SET CONFIG_VALUE = 'FALSE' WHERE CONFIG_KEY = 'DRY_RUN';

-- Turn on email approvals
UPDATE FINOPS_GUARDIAN.PUBLIC.AGENT_CONFIG SET CONFIG_VALUE = 'you@example.com' WHERE CONFIG_KEY = 'ALERT_RECIPIENT';
```

`DRY_RUN` defaults to TRUE on purpose: installing this project should never change a warehouse
until you say so. The remediation path, audit trail and approval flow behave identically in either
mode — only the `EXECUTE IMMEDIATE` is skipped.

### Enable scheduled monitoring

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

---

# Snowflake objects

| Object | Type | Purpose |
|---|---|---|
| `FINOPS_GUARDIAN` | Database | Project home |
| `AGENT_CONFIG` | Table | Runtime switches (DRY_RUN, credit rate, email recipient, token TTL) |
| `AGENT_SKILLS` | Table | Skill registry mirroring `.snowflake/cortex/skills/` |
| `AGENT_EXECUTION_LOG` | Table | Per-step skill trace, written live during a run |
| `REMEDIATION_ACTIONS` | Table | The toolkit: SQL templates, risk, approval gate |
| `USAGE_ANOMALIES` | Table | Anomalies with severity, recommended action, detecting skill |
| `AUDIT_LOG` | Table | Full action history including approval channel |
| `SAVINGS_HISTORY` | Table | Daily savings snapshots |
| `APPROVAL_TOKENS` | Table | Single-use expiring tokens for email approvals |
| `SMART_ALERTS` | Table | Natural-language rules parsed by Cortex |
| `NOTIFICATIONS` | Table | In-app notification events |
| `WAREHOUSE_METERING_TEST` | Table | Synthetic metering data, generated relative to today |
| `WAREHOUSE_CONFIG_TEST` | Table | Synthetic warehouse sizes for the optimizer skill |
| `QUERY_HISTORY_TEST` | Table | Synthetic query history for the watchdog skill |
| `LOG_AGENT_STEP` | Procedure | Opens and closes one trace step in place |
| `NOTIFY` | Procedure | Raises an in-app notification |
| `DETECT_IDLE_COMPUTE` | Procedure | Idle scan against `ACCOUNT_USAGE` |
| `DETECT_IDLE_COMPUTE_DEMO` | Procedure | Idle scan against demo data |
| `DETECT_COST_SPIKE_DEMO` | Procedure | Rolling-average spike detection |
| `DETECT_OVERSIZED_WAREHOUSE` | Procedure | Peak-vs-capacity utilisation check |
| `DETECT_LONG_RUNNING_QUERIES` | Procedure | Runtime budget check with user/role attribution |
| `APPLY_FIXES` | Procedure | Matches anomalies to toolkit actions, applies or queues |
| `EXECUTE_REMEDIATION` | Procedure | Renders and runs one action, honouring `DRY_RUN` |
| `APPROVE_FIX` | Procedure | Approve, with optional action override |
| `REJECT_FIX` | Procedure | Reject a proposed remediation |
| `GENERATE_APPROVAL_TOKEN` | Procedure | Mints a single-use approval token |
| `CONSUME_APPROVAL_TOKEN` | Procedure | Validates and redeems a token, server-side |
| `SEND_APPROVAL_EMAIL` | Procedure | Builds the links and emails them; returns them as JSON |
| `SEND_PENDING_APPROVAL_EMAILS` | Procedure | Bulk dispatch for the alert |
| `EVALUATE_SMART_ALERTS` | Procedure | Evaluates parsed NL rules against metering data |
| `SNAPSHOT_SAVINGS` | Procedure | Daily savings rollup |
| `TASK_DETECT_IDLE` … `TASK_SNAPSHOT_SAVINGS` | Tasks | Hourly detection → remediation → alerts → snapshot chain |
| `HIGH_SEVERITY_ALERT` | Alert | Emails approval links every 15 minutes |
| `FINOPS_ALERTS` | Integration | Email notification channel |

---

# Tech stack

- **Snowflake Cortex AI (`llama3.1-70b`)** — grounded cost reasoning and natural-language rule parsing
- **CoCo CLI agent skills** — seven skills in `.snowflake/cortex/skills/`, mirrored in `AGENT_SKILLS`
  and traced per step in `AGENT_EXECUTION_LOG`
- **Snowflake** — stored procedures, task chain, alerts, email notification integration
- **Streamlit-in-Snowflake** — dashboard with cached reads, bound-parameter writes, live skill trace
- **Altair** — charts rendered alongside the AI answers from the same evidence
- **SQL** — all detection and remediation logic runs natively in Snowflake, zero external compute

---

# Security notes

- Every value reaching SQL is a **bind parameter** — Cortex prompts, LLM-parsed alert fields,
  approval tokens, audit filters. Nothing user- or model-supplied is concatenated into a statement.
- The alert parser's output is **clamped to a fixed vocabulary** before storage, so a
  prompt-injected metric name cannot become SQL.
- Approval tokens are validated **server-side** in `CONSUME_APPROVAL_TOKEN` — format, expiry,
  single use, action match — and the redeemer's Snowflake identity, not the token, is recorded.
- The chat prompt carries an explicit **prompt-injection guard** and a topic restriction.
- Database values rendered into HTML are escaped with `html.escape`.
- `DRY_RUN` defaults to `TRUE`, so the agent cannot alter a warehouse until explicitly enabled.
- The app resolves `st.rerun` / `st.experimental_rerun` and both query-parameter APIs at runtime,
  so a Streamlit-in-Snowflake version bump cannot break it.

---

## License

MIT
