# Plan: FinOps Guardian v0.3 Features + README Update

## Context

Current app (v0.2) has: KPI cards with $ savings, anomaly bar chart, cost trend timeline, warehouse status panel, pending approvals with AI insights, query drilldown, auto-applied fixes table, audit log, and sidebar controls. The README documents v0.1 features only.

Key files:
- [streamlit_app.py](d:\FinOpsGuardian\streamlit_app.py) — Main dashboard (will add new sections)
- [setup.sql](d:\FinOpsGuardian\setup.sql) — Backend SQL (will add new tables, tasks, alert)
- [README.md](d:\FinOpsGuardian\README.md) — Documentation (will rewrite with all features)

## Implementation Steps

### Step 1: Create SAVINGS_HISTORY table and seed 7 days of synthetic data

Add to `setup.sql` and execute:
- `SAVINGS_HISTORY` table (date, anomalies, credits_wasted, credits_saved, dollar_saved)
- `SNAPSHOT_SAVINGS()` procedure to capture daily totals
- Seed 7 days of growing savings data for demo chart

### Step 2: Add savings trend line chart to dashboard

New section after KPI cards showing cumulative savings over 7 days. Uses `st.line_chart` with the SAVINGS_HISTORY table.

### Step 3: Add week-over-week comparison section

Query `WAREHOUSE_METERING_HISTORY` (real data) and `WAREHOUSE_METERING_TEST` (demo fallback). Show `st.metric` cards with delta values per warehouse. Handles sparse data gracefully.

### Step 4: Add cost attribution by user/role section

Query `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` for top users by credit consumption (last 7 days). Display as bar chart + table. Wrapped in try/except since new accounts have limited history.

### Step 5: Add AI chat assistant to sidebar

Add a text input in the sidebar. On submit, build context from current anomalies/audit data and call `snowflake.cortex.Complete("mistral-large2", prompt)`. Display response as markdown.

### Step 6: Create scheduled tasks and alert for automated monitoring

SQL objects:
- `TASK_DETECT_IDLE` — runs `DETECT_IDLE_COMPUTE(24)` hourly
- `TASK_DETECT_SPIKE` — runs `DETECT_COST_SPIKE_DEMO(2.5)` hourly
- `TASK_APPLY_FIXES` — runs after both detection tasks complete
- `FINOPS_ALERTS` notification integration (email)
- `HIGH_SEVERITY_ALERT` — emails on new HIGH/CRITICAL anomalies

### Step 7: Add monitoring status card to dashboard

Show task status (SHOW TASKS) and last execution time in a small status panel near the top.

### Step 8: Rewrite README.md with all features

Complete rewrite covering:
- Updated "What It Does" with all v0.3 capabilities
- Updated architecture diagram (adding Tasks, Alerts, Cortex AI)
- New "Features" section with all 12+ features listed
- Updated "Snowflake Objects Created" table (new tables, tasks, alert)
- Updated demo flow (including Reset Demo, AI chat, scheduled monitoring)
- Updated tech stack (adding Cortex AI)
- Screenshots section placeholder

### Step 9: Re-upload to stage, verify, and push to GitHub

Upload updated `streamlit_app.py`, verify in Snowsight, commit all changes, push.

## Verification

- Refresh the Streamlit app in Snowsight — all sections render without errors
- Savings trend chart shows 7 days of data
- WoW comparison shows metrics (may be sparse on new account)
- AI chat responds to a question like "what's wasting the most?"
- `SHOW TASKS` confirms tasks are created (suspended by default)
- README renders correctly on GitHub

## Critical Files

- `d:\FinOpsGuardian\streamlit_app.py` — Add 5 new dashboard sections + AI chat
- `d:\FinOpsGuardian\setup.sql` — Add SAVINGS_HISTORY table, tasks, alert, seed data
- `d:\FinOpsGuardian\README.md` — Complete rewrite with all features documented
