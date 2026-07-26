import os
import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(
    page_title="FinOps Guardian",
    page_icon="🛡️",
    layout="wide",
)

# --- Connection ---
@st.cache_resource
def get_session():
    try:
        return get_active_session()
    except Exception:
        import snowflake.connector
        conn = st.connection("snowflake")
        return conn.session()


session = get_session()

DB = "FINOPS_GUARDIAN"
SCHEMA = "PUBLIC"


def run_query(sql):
    return session.sql(sql).to_pandas()


# --- Header ---
st.title("FinOps Guardian")
st.caption("AI-powered Snowflake warehouse cost monitoring & anomaly detection")

# --- Section 1: Summary Metrics ---
summary = run_query(f"""
    SELECT
        COUNT(*) AS total_anomalies,
        SUM(CREDITS_WASTED) AS total_credits_wasted,
        SUM(CASE WHEN STATUS = 'RESOLVED' THEN CREDITS_WASTED ELSE 0 END) AS credits_saved,
        COUNT(CASE WHEN STATUS = 'OPEN' OR STATUS = 'ACKNOWLEDGED' THEN 1 END) AS open_issues
    FROM {DB}.{SCHEMA}.USAGE_ANOMALIES
""")

col1, col2, col3, col4 = st.columns(4)
total_wasted = float(summary["TOTAL_CREDITS_WASTED"].iloc[0] or 0)
credits_saved = float(summary["CREDITS_SAVED"].iloc[0] or 0)
col1.metric("Total Anomalies Detected", int(summary["TOTAL_ANOMALIES"].iloc[0]))
col2.metric("Credits Wasted", f"{total_wasted:.4f}")
col3.metric("Potential Savings (Resolved)", f"{credits_saved:.4f}")
col4.metric("Open Issues", int(summary["OPEN_ISSUES"].iloc[0]))

st.divider()

# --- Section 2: Anomaly Chart by Warehouse ---
st.subheader("Anomalies by Warehouse & Type")

chart_data = run_query(f"""
    SELECT WAREHOUSE_NAME, ANOMALY_TYPE, COUNT(*) AS COUNT, SUM(CREDITS_WASTED) AS CREDITS
    FROM {DB}.{SCHEMA}.USAGE_ANOMALIES
    GROUP BY WAREHOUSE_NAME, ANOMALY_TYPE
    ORDER BY CREDITS DESC
""")

if not chart_data.empty:
    col_chart, col_table = st.columns([2, 1])
    with col_chart:
        st.bar_chart(chart_data, x="WAREHOUSE_NAME", y="CREDITS", color="ANOMALY_TYPE")
    with col_table:
        st.dataframe(chart_data, use_container_width=True, hide_index=True)
else:
    st.info("No anomalies detected yet. Run detection procedures to populate data.")

st.divider()

# --- Section 3: Pending Approvals (HIGH/CRITICAL) ---
st.subheader("Pending Approvals")
st.caption("HIGH and CRITICAL severity fixes require human approval before application.")

pending = run_query(f"""
    SELECT
        a.ANOMALY_ID,
        a.WAREHOUSE_NAME,
        a.ANOMALY_TYPE,
        a.SEVERITY,
        a.CREDITS_WASTED,
        a.DESCRIPTION,
        l.SQL_EXECUTED AS PROPOSED_FIX,
        l.ACTION_DETAILS
    FROM {DB}.{SCHEMA}.USAGE_ANOMALIES a
    JOIN {DB}.{SCHEMA}.AUDIT_LOG l ON l.ANOMALY_ID = a.ANOMALY_ID
    WHERE a.STATUS = 'ACKNOWLEDGED'
      AND l.STATUS = 'PENDING_APPROVAL'
    ORDER BY a.CREDITS_WASTED DESC
""")

if not pending.empty:
    for idx, row in pending.iterrows():
        with st.container(border=True):
            pcol1, pcol2, pcol3 = st.columns([3, 2, 1])
            with pcol1:
                st.markdown(f"**{row['WAREHOUSE_NAME']}** — {row['ANOMALY_TYPE']}")
                st.text(row["DESCRIPTION"])
            with pcol2:
                st.code(row["PROPOSED_FIX"], language="sql")
                st.caption(f"Severity: **{row['SEVERITY']}** | Credits at risk: {float(row['CREDITS_WASTED']):.4f}")
            with pcol3:
                anomaly_id = int(row["ANOMALY_ID"])
                if st.button("Approve", key=f"approve_{anomaly_id}", type="primary"):
                    session.sql(
                        f"CALL {DB}.{SCHEMA}.APPROVE_FIX({anomaly_id}, CURRENT_USER())"
                    ).collect()
                    st.success(f"Approved anomaly {anomaly_id}")
                    st.rerun()
                if st.button("Dismiss", key=f"dismiss_{anomaly_id}"):
                    session.sql(f"""
                        UPDATE {DB}.{SCHEMA}.USAGE_ANOMALIES
                        SET STATUS = 'DISMISSED'
                        WHERE ANOMALY_ID = {anomaly_id}
                    """).collect()
                    session.sql(f"""
                        UPDATE {DB}.{SCHEMA}.AUDIT_LOG
                        SET STATUS = 'COMPLETED', APPROVED_BY = CURRENT_USER()
                        WHERE ANOMALY_ID = {anomaly_id} AND STATUS = 'PENDING_APPROVAL'
                    """).collect()
                    st.warning(f"Dismissed anomaly {anomaly_id}")
                    st.rerun()
else:
    st.success("No pending approvals. All high-severity issues have been addressed.")

st.divider()

# --- Section 4: Recently Auto-Applied Fixes ---
st.subheader("Auto-Applied Fixes (LOW/MEDIUM)")

auto_fixes = run_query(f"""
    SELECT
        l.LOGGED_AT,
        l.WAREHOUSE_NAME,
        a.ANOMALY_TYPE,
        a.SEVERITY,
        l.ACTION_DETAILS,
        l.SQL_EXECUTED
    FROM {DB}.{SCHEMA}.AUDIT_LOG l
    JOIN {DB}.{SCHEMA}.USAGE_ANOMALIES a ON a.ANOMALY_ID = l.ANOMALY_ID
    WHERE l.ACTION_TYPE = 'AUTO_ACTION'
      AND l.STATUS = 'COMPLETED'
    ORDER BY l.LOGGED_AT DESC
    LIMIT 20
""")

if not auto_fixes.empty:
    st.dataframe(
        auto_fixes,
        use_container_width=True,
        hide_index=True,
        column_config={
            "LOGGED_AT": st.column_config.DatetimeColumn("Applied At", format="MM/DD HH:mm"),
            "SQL_EXECUTED": st.column_config.TextColumn("SQL Fix", width="large"),
        },
    )
else:
    st.info("No auto-applied fixes yet.")

st.divider()

# --- Section 5: Full Audit Log ---
st.subheader("Audit Log")

# Filters
fcol1, fcol2, fcol3 = st.columns(3)
with fcol1:
    warehouses = run_query(f"""
        SELECT DISTINCT WAREHOUSE_NAME FROM {DB}.{SCHEMA}.AUDIT_LOG
        WHERE WAREHOUSE_NAME IS NOT NULL ORDER BY 1
    """)
    wh_options = ["All"] + warehouses["WAREHOUSE_NAME"].tolist()
    wh_filter = st.selectbox("Warehouse", wh_options)
with fcol2:
    status_options = ["All", "COMPLETED", "PENDING_APPROVAL", "FAILED"]
    status_filter = st.selectbox("Status", status_options)
with fcol3:
    action_options = ["All", "DETECTION", "AUTO_ACTION", "RECOMMENDATION", "USER_ACTION"]
    action_filter = st.selectbox("Action Type", action_options)

where_clauses = []
if wh_filter != "All":
    where_clauses.append(f"WAREHOUSE_NAME = '{wh_filter}'")
if status_filter != "All":
    where_clauses.append(f"STATUS = '{status_filter}'")
if action_filter != "All":
    where_clauses.append(f"ACTION_TYPE = '{action_filter}'")

where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

audit_log = run_query(f"""
    SELECT LOG_ID, LOGGED_AT, ACTION_TYPE, ANOMALY_ID, WAREHOUSE_NAME,
           ACTION_DETAILS, SQL_EXECUTED, APPROVED_BY, STATUS, ERROR_MESSAGE
    FROM {DB}.{SCHEMA}.AUDIT_LOG
    {where_sql}
    ORDER BY LOGGED_AT DESC
    LIMIT 50
""")

st.dataframe(
    audit_log,
    use_container_width=True,
    hide_index=True,
    column_config={
        "LOGGED_AT": st.column_config.DatetimeColumn("Timestamp", format="MM/DD HH:mm:ss"),
        "ACTION_DETAILS": st.column_config.TextColumn("Details", width="large"),
    },
)

# --- Sidebar: Run Detection ---
with st.sidebar:
    st.header("Agent Controls")
    st.caption("Run detection scans and apply fixes manually.")

    if st.button("Run Idle Compute Detection", use_container_width=True):
        result = session.sql(f"CALL {DB}.{SCHEMA}.DETECT_IDLE_COMPUTE_DEMO()").collect()
        st.success(result[0][0])
        st.rerun()

    if st.button("Run Cost Spike Detection", use_container_width=True):
        result = session.sql(f"CALL {DB}.{SCHEMA}.DETECT_COST_SPIKE_DEMO(2.5)").collect()
        st.success(result[0][0])
        st.rerun()

    if st.button("Apply Fixes", use_container_width=True, type="primary"):
        result = session.sql(f"CALL {DB}.{SCHEMA}.APPLY_FIXES()").collect()
        st.success(result[0][0])
        st.rerun()

    st.divider()
    st.caption("FinOps Guardian v0.1 | Hackathon Demo")
