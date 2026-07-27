# Plan: Improve FinOps Guardian Dashboard

## Overview

Add 6 high-impact features to make the hackathon demo more compelling. All features use SiS-compatible Streamlit (no `st.rerun`, no `hide_index`, no `color=` in charts).

## Feature Details

### 1. Cost Trend Timeline (7-day line chart)

Add a new section below the bar chart with a time-series line chart showing hourly credit usage per warehouse. Uses `WAREHOUSE_METERING_TEST` for demo data. Pivots by warehouse name so each warehouse is a separate line.

```python
st.subheader("Credit Usage Timeline")
timeline = run_query("""
    SELECT DATE_TRUNC('hour', START_TIME) AS HOUR, WAREHOUSE_NAME, CREDITS_USED
    FROM FINOPS_GUARDIAN.PUBLIC.WAREHOUSE_METERING_TEST
    ORDER BY HOUR
""")
pivot_time = timeline.pivot_table(index="HOUR", columns="WAREHOUSE_NAME", values="CREDITS_USED", aggfunc="sum").fillna(0)
st.line_chart(pivot_time)
```

### 2. Estimated $ Savings

Add dollar conversion at $3/credit (Snowflake standard enterprise rate). Update KPI cards:
- "Credits Wasted" → also show `($X.XX)`
- Add a 5th metric: "Estimated Annual Savings" projected from resolved anomalies

### 3. AI-Generated Insights (Cortex COMPLETE)

For each pending or recent anomaly, call Cortex to generate a plain-English explanation:

```python
import snowflake.cortex as cortex

prompt = f"""You are a FinOps expert. Analyze this Snowflake warehouse anomaly and provide:
1. Likely root cause (1-2 sentences)
2. Recommended action (1 sentence)
3. Estimated impact if not addressed (1 sentence)

Anomaly: {row['DESCRIPTION']}
Warehouse: {row['WAREHOUSE_NAME']}
Type: {row['ANOMALY_TYPE']}
Severity: {row['SEVERITY']}
Credits at risk: {row['CREDITS_WASTED']}"""

insight = cortex.Complete("mistral-large2", prompt)
```

Display in an expandable section under each anomaly card.

### 4. Reset Demo Button

Sidebar button that:
1. Truncates both tables
2. Calls DETECT_IDLE_COMPUTE_DEMO()
3. Calls DETECT_COST_SPIKE_DEMO(2.5)
4. Calls APPLY_FIXES()

Restores the demo to: 9 resolved + 1 pending approval.

### 5. Real-Time Warehouse Status

New section showing live warehouse state:

```python
st.subheader("Warehouse Status (Live)")
wh_status = run_query("SHOW WAREHOUSES")
# Display: NAME, STATE, SIZE, AUTO_SUSPEND, RUNNING queries
```

Format as a colored status table (STARTED = active, SUSPENDED = grey).

### 6. Query-Level Drilldown

For COST_SPIKE anomalies, add an expander showing the top expensive queries during the spike window:

```python
queries = run_query(f"""
    SELECT QUERY_ID, USER_NAME, WAREHOUSE_NAME,
           EXECUTION_STATUS, TOTAL_ELAPSED_TIME/1000 AS SECONDS,
           CREDITS_USED_CLOUD_SERVICES,
           SUBSTR(QUERY_TEXT, 1, 100) AS QUERY_PREVIEW
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE WAREHOUSE_NAME = '{wh}'
      AND START_TIME BETWEEN '{start}' AND '{end}'
    ORDER BY TOTAL_ELAPSED_TIME DESC
    LIMIT 5
""")
```

## Layout (top to bottom)

1. **Title + KPI cards** (with $ amounts)
2. **Anomaly bar chart** (existing) + **Cost trend timeline** (new)
3. **Warehouse Status (Live)** (new)
4. **Pending Approvals** (with AI insights)
5. **Query Drilldown** (for cost spikes)
6. **Auto-Applied Fixes**
7. **Audit Log**
8. **Sidebar**: Agent Controls + Reset Demo

## Compatibility Notes

- Use `st.experimental_rerun()` (not `st.rerun()`)
- Use pivot + `st.line_chart(df)` (no `color=` param)
- No `hide_index`, no `column_config`
- `snowflake.cortex.Complete()` is available in SiS natively
- `SHOW WAREHOUSES` returns a DataFrame via `session.sql().to_pandas()`
