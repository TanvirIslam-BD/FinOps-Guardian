# FinOps Guardian

AI-powered Snowflake warehouse cost monitoring and anomaly detection agent with a human-in-the-loop approval workflow.

## What It Does

FinOps Guardian continuously monitors Snowflake warehouse usage, detects cost anomalies, and suggests concrete fixes — all with a full audit trail.

### Detection Engine

| Anomaly Type | Detection Logic |
|---|---|
| **Idle Compute** | Warehouse running (cloud services charges > 0) but no query execution (compute = 0) |
| **Cost Spike** | Hourly credits exceed 2.5x the rolling 3-hour average for that warehouse |

### Automated Fix Layer

- **LOW/MEDIUM severity** — Auto-applied immediately (e.g., reduce `AUTO_SUSPEND` to 60s). Logged with full audit trail.
- **HIGH/CRITICAL severity** — Queued as `PENDING_APPROVAL`. A human must click **Approve** or **Dismiss** in the dashboard before any action is taken.

### Audit Trail

Every detection, recommendation, and action is logged to `AUDIT_LOG` with:
- What was detected
- What fix was proposed (including the exact SQL)
- Who approved it (or if it was auto-applied)
- Whether it succeeded or failed

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Streamlit Dashboard                  │
│  KPI Cards │ Anomaly Chart │ Approvals │ Audit Log  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              Stored Procedures (SQL)                  │
│  DETECT_IDLE_COMPUTE │ DETECT_COST_SPIKE │ APPLY_FIX│
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              Snowflake Tables                         │
│  USAGE_ANOMALIES │ AUDIT_LOG │ METERING_TEST        │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│        SNOWFLAKE.ACCOUNT_USAGE                       │
│        WAREHOUSE_METERING_HISTORY                    │
└─────────────────────────────────────────────────────┘
```

## Live Demo

The app is deployed to Streamlit-in-Snowflake. The sidebar provides buttons to run detection scans and apply fixes in real-time during a demo.

**Demo flow for judges:**
1. Click **Run Idle Compute Detection** → detects idle warehouses
2. Click **Run Cost Spike Detection** → finds the 4x cost spike on ETL_WH
3. Click **Apply Fixes** → auto-resolves LOW/MEDIUM, queues HIGH for approval
4. Click **Approve** on the ETL_WH cost spike → resolves with your name in the audit log

## Project Structure

```
FinOpsGuardian/
├── streamlit_app.py       # Dashboard (deployed to Streamlit-in-Snowflake)
├── snowflake.yml          # SiS deployment manifest
├── pyproject.toml         # Python dependencies
├── setup.sql              # All SQL to recreate the backend (tables, procedures)
└── .streamlit/
    └── config.toml        # Dark theme with Snowflake blue accent
```

## Setup

### Prerequisites

- Snowflake account with `ACCOUNTADMIN` or equivalent role
- Access to `SNOWFLAKE.ACCOUNT_USAGE` views

### Deploy

1. Run `setup.sql` in a Snowflake worksheet to create the database, tables, procedures, and seed demo data.
2. Upload `streamlit_app.py` to the stage:
   ```sql
   PUT 'file://./streamlit_app.py' @FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
   ```
3. The Streamlit app object is created by `setup.sql` and will be available under **Projects → Streamlit** in Snowsight.

## Snowflake Objects Created

| Object | Type | Purpose |
|---|---|---|
| `FINOPS_GUARDIAN` | Database | Project home |
| `USAGE_ANOMALIES` | Table | Detected anomalies with severity, fix, status |
| `AUDIT_LOG` | Table | Full action history for governance |
| `WAREHOUSE_METERING_TEST` | Table | Synthetic demo data |
| `DETECT_IDLE_COMPUTE` | Procedure | Scans real account usage data |
| `DETECT_IDLE_COMPUTE_DEMO` | Procedure | Scans synthetic test data |
| `DETECT_COST_SPIKE_DEMO` | Procedure | Rolling average spike detection |
| `APPLY_FIXES` | Procedure | Generates and applies/queues fixes |
| `APPROVE_FIX` | Procedure | Human approval workflow |

## Tech Stack

- **Snowflake** — Data warehouse, stored procedures, Streamlit-in-Snowflake hosting
- **Streamlit** — Interactive dashboard with real-time controls
- **SQL** — All detection logic runs natively in Snowflake (no external compute)

## License

MIT
