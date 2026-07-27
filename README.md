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

| Anomaly Type | Detection Logic |
|---|---|
| **Idle Compute** | Warehouse running (cloud services > 0) but no query execution (compute = 0) |
| **Cost Spike** | Hourly credits exceed 2.5x the rolling 3-hour average |

### Automated Remediation

- **LOW/MEDIUM severity** -- Auto-applied immediately (e.g., `ALTER WAREHOUSE SET AUTO_SUSPEND = 60`)
- **HIGH/CRITICAL severity** -- Queued as `PENDING_APPROVAL` with human-in-the-loop approval

### Smart Alerts -- Natural Language (AI-Powered)

- **Plain English rules** -- Create monitoring alerts using natural language (e.g., "Notify me if any warehouse spends more than $50 per day")
- **Cortex AI parsing** -- Rules are parsed by Snowflake Cortex AI (Mistral Large 2) into structured JSON with metric, threshold, warehouse, and condition
- **Visual rule display** -- Parsed alert rules shown as colored tags for metric, threshold, and target warehouse
- **Active alerts management** -- View, activate, and delete alerts from the UI
- **Persistent storage** -- Alerts stored in `SMART_ALERTS` table with trigger tracking

### AI-Powered Insights (Cortex AI)

- **Anomaly Analysis** -- Each pending anomaly gets a Cortex LLM-generated root cause analysis, recommended action, and impact assessment
- **AI Chat Assistant** -- Ask natural language questions about your costs (e.g., "what's wasting the most money?") and get answers grounded in your anomaly data
- **Cost Attribution** -- AI-enhanced breakdown of credit consumption by user/role
- **Week-over-Week Analysis** -- Per-warehouse credit usage with % change indicators

### Operations Center

- **Real-time warehouse status** -- Live view of all warehouses (RUNNING/SUSPENDED, size, auto-suspend, queued queries)
- **Auto-fix history** -- Timeline of all automated remediation actions taken
- **Query-level drilldown** -- For cost spikes, shows the actual expensive queries that caused it

### Human-in-the-Loop Approvals

- **Pending recommendations** -- HIGH/CRITICAL fixes queued for manual review
- **AI analysis per anomaly** -- Cortex-generated root cause, recommendation, and impact before you approve
- **One-click approve** -- Apply the recommended fix with full audit logging
- **Recently approved** -- History of past approvals with timestamps

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

- **Hourly detection tasks** -- Snowflake Tasks run idle compute and cost spike detection every hour
- **Automated fix application** -- Downstream task applies fixes after detection completes
- **Email alerts** -- HIGH/CRITICAL severity anomalies trigger email notifications via Snowflake notification integration

### Performance Optimizations

- **Query caching** -- All read-only dashboard queries cached with 120s TTL for instant tab switching
- **Single-click navigation** -- Immediate tab switching with `experimental_rerun()`
- **Smooth transitions** -- CSS animations for content loading (fadeIn)
- **Light theme enforcement** -- Forced light theme via `config.toml` for consistent rendering

### Demo Controls

- **One-click reset** -- Wipe and re-seed all data for a clean live demo
- **Quick Actions** -- Upload Scan (detect idle), Explorer (detect spikes), New Scan (apply fixes)
- **Scan profiles** -- Configurable scan presets

## Architecture

```
+-----------------------------------------------------------+
|                    Streamlit Dashboard                      |
|  Executive Summary | Operations | Approvals | Intelligence |
|  Compliance | Notifications | Audit Trail                 |
+-----------------------------+-----------------------------+
                              |
+-----------------------------v-----------------------------+
|              Cortex AI (Mistral Large 2)                   |
|  NL Alert Parsing | Chat Assistant | Anomaly Analysis     |
+-----------------------------+-----------------------------+
                              |
+-----------------------------v-----------------------------+
|              Snowflake Tasks (Hourly)                      |
|  TASK_DETECT_IDLE --> TASK_APPLY_FIXES                    |
|  TASK_DETECT_SPIKE -->                                    |
+-----------------------------+-----------------------------+
                              |
+-----------------------------v-----------------------------+
|              Stored Procedures                             |
|  DETECT_IDLE_COMPUTE | DETECT_COST_SPIKE | APPLY_FIXES   |
|  APPROVE_FIX | SNAPSHOT_SAVINGS                           |
+-----------------------------+-----------------------------+
                              |
+-----------------------------v-----------------------------+
|              Snowflake Tables                              |
|  USAGE_ANOMALIES | AUDIT_LOG | SAVINGS_HISTORY           |
|  SMART_ALERTS | NOTIFICATIONS | WAREHOUSE_METERING_TEST  |
+-----------------------------+-----------------------------+
                              |
+-----------------------------v-----------------------------+
|              Snowflake Platform                            |
|  ACCOUNT_USAGE | Cortex AI | Notifications | Alerts      |
+-----------------------------------------------------------+
```

## Live Demo

The app is deployed to Streamlit-in-Snowflake with a polished sidebar UI and instant navigation.

**Demo flow for judges:**

1. Click **Reset Demo** -- restores clean state with 9 auto-resolved + 1 pending anomaly
2. Observe **KPI cards** -- 10 anomalies, credits wasted, dollars saved, CO2 avoided
3. See **Savings Trend** -- 7-day chart showing growing savings
4. Check **Warehouse Health Scores** -- live health rating for each warehouse
5. Go to **Operations** -- see real-time warehouse status and auto-fix history
6. Go to **Approvals** -- review pending HIGH severity anomaly with AI analysis, click Approve
7. Go to **Intelligence** -- ask the AI "what's wasting the most money?"
8. Create a **Smart Alert** -- type "Notify me if any warehouse spends more than $50 per day" and see AI parse it
9. Go to **Compliance** -- see policy check results and recommendations
10. Show **Audit Trail** -- full paper trail of everything that happened

## Project Structure

```
FinOpsGuardian/
├── streamlit_app.py       # Dashboard (deployed to Streamlit-in-Snowflake)
├── setup.sql              # All SQL to recreate the backend
├── snowflake.yml          # SiS deployment manifest
├── pyproject.toml         # Python dependencies
├── README.md              # This file
└── .streamlit/
    └── config.toml        # Light theme with purple accent
```

## Setup

### Prerequisites

- Snowflake account with `ACCOUNTADMIN` role
- Cortex AI enabled (for LLM features -- Mistral Large 2)
- Warehouse `COMPUTE_WH` available

### Deploy

1. Run `setup.sql` in a Snowflake worksheet to create all objects and seed demo data
2. Upload the app to the stage:
   ```sql
   PUT 'file://./streamlit_app.py' @FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
   PUT 'file://./.streamlit/config.toml' @FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE/.streamlit/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
   ```
3. The Streamlit app will be available under **Projects > Streamlit > FinOps Guardian** in Snowsight

### Enable Scheduled Monitoring

```sql
ALTER TASK FINOPS_GUARDIAN.PUBLIC.TASK_APPLY_FIXES RESUME;
ALTER TASK FINOPS_GUARDIAN.PUBLIC.TASK_DETECT_IDLE RESUME;
ALTER TASK FINOPS_GUARDIAN.PUBLIC.TASK_DETECT_SPIKE RESUME;
ALTER ALERT FINOPS_GUARDIAN.PUBLIC.HIGH_SEVERITY_ALERT RESUME;
```

## Snowflake Objects

| Object | Type | Purpose |
|---|---|---|
| `FINOPS_GUARDIAN` | Database | Project home |
| `USAGE_ANOMALIES` | Table | Detected anomalies with severity, fix, status |
| `AUDIT_LOG` | Table | Full action history for governance |
| `SAVINGS_HISTORY` | Table | Daily savings snapshots for trend chart |
| `SMART_ALERTS` | Table | Natural language alert rules parsed by AI |
| `NOTIFICATIONS` | Table | In-app notification events |
| `WAREHOUSE_METERING_TEST` | Table | Synthetic demo data |
| `DETECT_IDLE_COMPUTE` | Procedure | Scans real account usage for idle warehouses |
| `DETECT_IDLE_COMPUTE_DEMO` | Procedure | Scans synthetic test data |
| `DETECT_COST_SPIKE_DEMO` | Procedure | Rolling average spike detection |
| `APPLY_FIXES` | Procedure | Generates and applies/queues fixes |
| `APPROVE_FIX` | Procedure | Human approval workflow |
| `TASK_DETECT_IDLE` | Task | Hourly idle compute scan |
| `TASK_DETECT_SPIKE` | Task | Hourly cost spike scan |
| `TASK_APPLY_FIXES` | Task | Auto-apply fixes after detection |
| `HIGH_SEVERITY_ALERT` | Alert | Email on HIGH/CRITICAL anomalies |
| `FINOPS_ALERTS` | Integration | Email notification channel |

## Tech Stack

- **Snowflake** -- Data warehouse, stored procedures, tasks, alerts, Streamlit-in-Snowflake
- **Cortex AI (Mistral Large 2)** -- NL alert parsing, anomaly analysis, chat assistant
- **Streamlit** -- Interactive dashboard with cached queries and instant navigation
- **SQL** -- All detection logic runs natively in Snowflake (zero external compute)
- **CSS/HTML** -- Custom-styled KPI cards, navigation, health scores, alert badges

## License

MIT
