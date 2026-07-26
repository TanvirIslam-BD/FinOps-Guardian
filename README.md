# FinOps Guardian

AI-powered Snowflake warehouse cost monitoring and anomaly detection agent with automated remediation, human-in-the-loop approval, and a full audit trail.

## Features

### Detection Engine

| Anomaly Type | Detection Logic |
|---|---|
| **Idle Compute** | Warehouse running (cloud services > 0) but no query execution (compute = 0) |
| **Cost Spike** | Hourly credits exceed 2.5x the rolling 3-hour average |

### Automated Remediation

- **LOW/MEDIUM severity** -- Auto-applied immediately (e.g., `ALTER WAREHOUSE SET AUTO_SUSPEND = 60`)
- **HIGH/CRITICAL severity** -- Queued as `PENDING_APPROVAL` with human-in-the-loop approval

### AI-Powered Insights (Cortex AI)

- **Anomaly Analysis** -- Each pending anomaly gets a Cortex LLM-generated root cause analysis, recommended action, and impact assessment
- **AI Chat Assistant** -- Ask natural language questions about your costs (e.g., "what's wasting the most money?") and get answers grounded in your anomaly data

### Scheduled Monitoring

- **Hourly detection tasks** -- Snowflake Tasks run idle compute and cost spike detection every hour
- **Automated fix application** -- Downstream task applies fixes after detection completes
- **Email alerts** -- HIGH/CRITICAL severity anomalies trigger email notifications via Snowflake notification integration

### Executive Reporting

- **Dollar savings** -- All metrics converted to $ at configurable credit rate ($3/credit default)
- **Savings trend** -- 7-day line chart showing cumulative savings over time (ROI proof)
- **Week-over-week comparison** -- Per-warehouse credit usage with % change indicators
- **Cost attribution** -- Top users/roles by credit consumption from QUERY_HISTORY

### Operational Visibility

- **Real-time warehouse status** -- Live view of all warehouses (RUNNING/SUSPENDED, size, auto-suspend)
- **Query-level drilldown** -- For cost spikes, shows the actual expensive queries that caused it
- **Full audit log** -- Every detection, recommendation, and action logged with who/what/when
- **Filterable history** -- Filter audit log by warehouse, status, and action type

### Demo Controls

- **One-click reset** -- Wipe and re-seed all data for a clean live demo
- **Manual scan buttons** -- Trigger detection and fix application on demand

## Architecture

```
+-----------------------------------------------------------+
|                    Streamlit Dashboard                      |
|  KPIs | Savings Trend | WoW | Attribution | Approvals     |
|  AI Chat | Warehouse Status | Audit Log                   |
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
|  WAREHOUSE_METERING_TEST                                  |
+-----------------------------+-----------------------------+
                              |
+-----------------------------v-----------------------------+
|              Snowflake Platform                            |
|  ACCOUNT_USAGE | Cortex AI | Notifications | Alerts      |
+-----------------------------------------------------------+
```

## Live Demo

The app is deployed to Streamlit-in-Snowflake with sidebar controls for real-time interaction.

**Demo flow for judges:**

1. Click **Reset Demo** -- restores clean state with 9 auto-resolved + 1 pending anomaly
2. Observe **KPI cards** -- 10 anomalies, $37.40 saved, 1 open issue
3. See **Savings Trend** -- 7-day chart showing growing savings
4. Check **Week-over-Week** -- real warehouse usage comparison
5. Review **Cost Attribution** -- who's spending the most
6. Click **Approve** on ETL_WH cost spike -- resolves with AI analysis visible
7. Ask the **AI Assistant** "what's wasting the most money?" -- get a natural language answer
8. Show **Audit Log** -- full paper trail of everything that happened

## Project Structure

```
FinOpsGuardian/
├── streamlit_app.py       # Dashboard (deployed to Streamlit-in-Snowflake)
├── setup.sql              # All SQL to recreate the backend
├── snowflake.yml          # SiS deployment manifest
├── pyproject.toml         # Python dependencies
├── README.md              # This file
└── .streamlit/
    └── config.toml        # Dark theme with Snowflake blue accent
```

## Setup

### Prerequisites

- Snowflake account with `ACCOUNTADMIN` role
- Access to `SNOWFLAKE.ACCOUNT_USAGE` views
- Cortex AI enabled (for LLM features)

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
- **Cortex AI** -- LLM-powered anomaly analysis and natural language chat assistant
- **Streamlit** -- Interactive dashboard with real-time controls
- **SQL** -- All detection logic runs natively in Snowflake (zero external compute)

## License

MIT
