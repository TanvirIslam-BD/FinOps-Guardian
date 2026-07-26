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
        conn = st.connection("snowflake")
        return conn.session()


session = get_session()

DB = "FINOPS_GUARDIAN"
SCHEMA = "PUBLIC"
CREDIT_RATE = 3.00  # $/credit (Snowflake Enterprise)


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

total_wasted = float(summary["TOTAL_CREDITS_WASTED"].iloc[0] or 0)
credits_saved = float(summary["CREDITS_SAVED"].iloc[0] or 0)
dollar_saved = credits_saved * CREDIT_RATE

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Anomalies Detected", int(summary["TOTAL_ANOMALIES"].iloc[0]))
col2.metric("Credits Wasted", f"{total_wasted:.2f}")
col3.metric("Credits Saved", f"{credits_saved:.2f}")
col4.metric("$ Saved", f"${dollar_saved:,.2f}")
col5.metric("Open Issues", int(summary["OPEN_ISSUES"].iloc[0]))

st.divider()

# --- Section 2: Savings Trend + Week-over-Week ---
trend_col, wow_col = st.columns(2)

with trend_col:
    st.subheader("Savings Trend (7 Days)")
    savings = run_query(f"""
        SELECT SNAPSHOT_DATE, DOLLAR_SAVED, TOTAL_CREDITS_SAVED
        FROM {DB}.{SCHEMA}.SAVINGS_HISTORY
        ORDER BY SNAPSHOT_DATE
    """)
    if not savings.empty:
        savings = savings.set_index("SNAPSHOT_DATE")
        st.line_chart(savings[["DOLLAR_SAVED"]])
    else:
        st.info("No savings history yet.")

with wow_col:
    st.subheader("Week-over-Week")
    try:
        wow = run_query(f"""
            SELECT WAREHOUSE_NAME,
                   SUM(CASE WHEN START_TIME >= DATE_TRUNC('week', CURRENT_DATE) THEN CREDITS_USED ELSE 0 END) AS THIS_WEEK,
                   SUM(CASE WHEN START_TIME >= DATEADD('week', -1, DATE_TRUNC('week', CURRENT_DATE))
                             AND START_TIME < DATE_TRUNC('week', CURRENT_DATE) THEN CREDITS_USED ELSE 0 END) AS LAST_WEEK
            FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
            WHERE START_TIME >= DATEADD('week', -2, CURRENT_DATE)
              AND WAREHOUSE_NAME != 'CLOUD_SERVICES_ONLY'
            GROUP BY WAREHOUSE_NAME
            HAVING THIS_WEEK > 0 OR LAST_WEEK > 0
            ORDER BY THIS_WEEK DESC
        """)
        if not wow.empty:
            for _, row in wow.iterrows():
                this_w = float(row["THIS_WEEK"] or 0)
                last_w = float(row["LAST_WEEK"] or 0)
                if last_w > 0:
                    pct = ((this_w - last_w) / last_w) * 100
                    delta_str = f"{pct:+.1f}%"
                else:
                    delta_str = "new"
                st.metric(row["WAREHOUSE_NAME"], f"{this_w:.2f} credits", delta_str)
        else:
            st.info("Not enough history for comparison.")
    except Exception:
        st.info("Week-over-week requires ACCOUNT_USAGE access.")

st.divider()

# --- Section 3: Charts ---
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("Anomalies by Warehouse")
    chart_data = run_query(f"""
        SELECT WAREHOUSE_NAME, ANOMALY_TYPE, COUNT(*) AS COUNT, SUM(CREDITS_WASTED) AS CREDITS
        FROM {DB}.{SCHEMA}.USAGE_ANOMALIES
        GROUP BY WAREHOUSE_NAME, ANOMALY_TYPE
        ORDER BY CREDITS DESC
    """)
    if not chart_data.empty:
        pivot = chart_data.pivot_table(
            index="WAREHOUSE_NAME", columns="ANOMALY_TYPE",
            values="CREDITS", aggfunc="sum"
        ).fillna(0)
        st.bar_chart(pivot)
    else:
        st.info("No anomalies detected yet.")

with chart_col2:
    st.subheader("Credit Usage Timeline")
    timeline = run_query(f"""
        SELECT START_TIME AS HOUR, WAREHOUSE_NAME, CREDITS_USED
        FROM {DB}.{SCHEMA}.WAREHOUSE_METERING_TEST
        ORDER BY HOUR
    """)
    if not timeline.empty:
        pivot_time = timeline.pivot_table(
            index="HOUR", columns="WAREHOUSE_NAME",
            values="CREDITS_USED", aggfunc="sum"
        ).fillna(0)
        st.line_chart(pivot_time)
    else:
        st.info("No timeline data available.")

st.divider()

# --- Section 4: Cost Attribution by User/Role ---
st.subheader("Cost Attribution (Top Users - Last 7 Days)")

try:
    attribution = run_query("""
        SELECT USER_NAME, ROLE_NAME,
               COUNT(*) AS QUERIES,
               ROUND(SUM(CREDITS_USED_CLOUD_SERVICES), 4) AS CREDITS,
               ROUND(SUM(CREDITS_USED_CLOUD_SERVICES) * 3.00, 2) AS DOLLARS
        FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
        WHERE START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
          AND CREDITS_USED_CLOUD_SERVICES > 0
        GROUP BY USER_NAME, ROLE_NAME
        ORDER BY CREDITS DESC
        LIMIT 10
    """)
    if not attribution.empty:
        attr_col1, attr_col2 = st.columns([2, 1])
        with attr_col1:
            attr_pivot = attribution.set_index("USER_NAME")[["DOLLARS"]]
            st.bar_chart(attr_pivot)
        with attr_col2:
            st.dataframe(attribution[["USER_NAME", "ROLE_NAME", "QUERIES", "DOLLARS"]], use_container_width=True)
    else:
        st.info("No query cost data in the last 7 days.")
except Exception:
    st.info("Cost attribution requires ACCOUNT_USAGE access.")

st.divider()

# --- Section 5: Warehouse Status (Live) ---
st.subheader("Warehouse Status (Live)")

try:
    session.sql("SHOW WAREHOUSES").collect()
    wh_raw = run_query("""
        SELECT "name" AS WAREHOUSE, "state" AS STATUS, "size" AS SIZE,
               "auto_suspend" AS AUTO_SUSPEND_SEC, "running" AS RUNNING, "queued" AS QUEUED
        FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
    """)
    if not wh_raw.empty:
        def state_icon(s):
            if s == "STARTED":
                return "🟢 RUNNING"
            elif s == "SUSPENDED":
                return "⏸️ SUSPENDED"
            return s

        wh_raw["STATUS"] = wh_raw["STATUS"].apply(state_icon)
        st.dataframe(wh_raw, use_container_width=True)
    else:
        st.info("No warehouses found.")
except Exception as e:
    st.warning(f"Could not fetch warehouse status: {e}")

st.divider()

# --- Section 6: Pending Approvals ---
st.subheader("Pending Approvals")
st.caption("HIGH and CRITICAL severity fixes require human approval.")

pending = run_query(f"""
    SELECT
        a.ANOMALY_ID, a.WAREHOUSE_NAME, a.ANOMALY_TYPE, a.SEVERITY,
        a.CREDITS_WASTED, a.DESCRIPTION,
        l.SQL_EXECUTED AS PROPOSED_FIX, l.ACTION_DETAILS
    FROM {DB}.{SCHEMA}.USAGE_ANOMALIES a
    JOIN {DB}.{SCHEMA}.AUDIT_LOG l ON l.ANOMALY_ID = a.ANOMALY_ID
    WHERE a.STATUS = 'ACKNOWLEDGED' AND l.STATUS = 'PENDING_APPROVAL'
    ORDER BY a.CREDITS_WASTED DESC
""")

if not pending.empty:
    for idx, row in pending.iterrows():
        st.markdown("---")
        pcol1, pcol2, pcol3 = st.columns([3, 2, 1])
        with pcol1:
            st.markdown(f"**{row['WAREHOUSE_NAME']}** — {row['ANOMALY_TYPE']}")
            st.text(row["DESCRIPTION"])
            dollar_risk = float(row["CREDITS_WASTED"]) * CREDIT_RATE
            st.caption(f"Severity: **{row['SEVERITY']}** | Credits: {float(row['CREDITS_WASTED']):.2f} | **${dollar_risk:.2f}**")
        with pcol2:
            st.code(row["PROPOSED_FIX"], language="sql")
            try:
                import snowflake.cortex as cortex
                prompt = (
                    "You are a FinOps expert. In 3 concise bullet points: "
                    "1) Root cause, 2) Fix, 3) Impact if ignored. "
                    f"Anomaly: {row['DESCRIPTION']}. "
                    f"Type: {row['ANOMALY_TYPE']}, Severity: {row['SEVERITY']}, "
                    f"Credits: {float(row['CREDITS_WASTED']):.2f}"
                )
                insight = cortex.Complete("mistral-large2", prompt)
                st.markdown("**AI Analysis:**")
                st.markdown(insight)
            except Exception:
                pass
        with pcol3:
            anomaly_id = int(row["ANOMALY_ID"])
            if st.button("Approve", key=f"approve_{anomaly_id}", type="primary"):
                session.sql(f"CALL {DB}.{SCHEMA}.APPROVE_FIX({anomaly_id}, CURRENT_USER())").collect()
                st.success(f"Approved!")
                st.experimental_rerun()
            if st.button("Dismiss", key=f"dismiss_{anomaly_id}"):
                session.sql(f"UPDATE {DB}.{SCHEMA}.USAGE_ANOMALIES SET STATUS='DISMISSED' WHERE ANOMALY_ID={anomaly_id}").collect()
                session.sql(f"UPDATE {DB}.{SCHEMA}.AUDIT_LOG SET STATUS='COMPLETED', APPROVED_BY=CURRENT_USER() WHERE ANOMALY_ID={anomaly_id} AND STATUS='PENDING_APPROVAL'").collect()
                st.experimental_rerun()

        if row["ANOMALY_TYPE"] == "COST_SPIKE":
            with st.expander("View queries during spike window"):
                try:
                    spike_queries = run_query(f"""
                        SELECT QUERY_ID, USER_NAME, EXECUTION_STATUS,
                               ROUND(TOTAL_ELAPSED_TIME/1000, 1) AS DURATION_SEC,
                               SUBSTR(QUERY_TEXT, 1, 120) AS QUERY_PREVIEW
                        FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                        WHERE WAREHOUSE_NAME = '{row['WAREHOUSE_NAME']}'
                          AND START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
                        ORDER BY TOTAL_ELAPSED_TIME DESC LIMIT 5
                    """)
                    if not spike_queries.empty:
                        st.dataframe(spike_queries, use_container_width=True)
                    else:
                        st.info("No query history available (demo data).")
                except Exception:
                    st.info("Query history not available.")
else:
    st.success("No pending approvals. All high-severity issues have been addressed.")

st.divider()

# --- Section 7: Auto-Applied Fixes ---
st.subheader("Auto-Applied Fixes (LOW/MEDIUM)")

auto_fixes = run_query(f"""
    SELECT l.LOGGED_AT, l.WAREHOUSE_NAME, a.ANOMALY_TYPE, a.SEVERITY,
           ROUND(a.CREDITS_WASTED * {CREDIT_RATE}, 2) AS DOLLAR_SAVED,
           l.ACTION_DETAILS, l.SQL_EXECUTED
    FROM {DB}.{SCHEMA}.AUDIT_LOG l
    JOIN {DB}.{SCHEMA}.USAGE_ANOMALIES a ON a.ANOMALY_ID = l.ANOMALY_ID
    WHERE l.ACTION_TYPE = 'AUTO_ACTION' AND l.STATUS = 'COMPLETED'
    ORDER BY l.LOGGED_AT DESC LIMIT 20
""")

if not auto_fixes.empty:
    st.dataframe(auto_fixes, use_container_width=True)
else:
    st.info("No auto-applied fixes yet.")

st.divider()

# --- Section 8: Audit Log ---
st.subheader("Audit Log")

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
           ACTION_DETAILS, SQL_EXECUTED, APPROVED_BY, STATUS
    FROM {DB}.{SCHEMA}.AUDIT_LOG {where_sql}
    ORDER BY LOGGED_AT DESC LIMIT 50
""")

st.dataframe(audit_log, use_container_width=True)

# --- Sidebar ---
with st.sidebar:
    st.header("Agent Controls")
    st.caption("Run detection scans and apply fixes.")

    if st.button("Run Idle Compute Detection", use_container_width=True):
        result = session.sql(f"CALL {DB}.{SCHEMA}.DETECT_IDLE_COMPUTE_DEMO()").collect()
        st.success(result[0][0])
        st.experimental_rerun()

    if st.button("Run Cost Spike Detection", use_container_width=True):
        result = session.sql(f"CALL {DB}.{SCHEMA}.DETECT_COST_SPIKE_DEMO(2.5)").collect()
        st.success(result[0][0])
        st.experimental_rerun()

    if st.button("Apply Fixes", use_container_width=True, type="primary"):
        result = session.sql(f"CALL {DB}.{SCHEMA}.APPLY_FIXES()").collect()
        st.success(result[0][0])
        st.experimental_rerun()

    st.divider()
    st.subheader("AI Assistant")
    user_q = st.text_input("Ask about your costs...")
    if user_q:
        try:
            import snowflake.cortex as cortex
            context_df = run_query(f"""
                SELECT WAREHOUSE_NAME, ANOMALY_TYPE, SEVERITY, CREDITS_WASTED, STATUS, DESCRIPTION
                FROM {DB}.{SCHEMA}.USAGE_ANOMALIES ORDER BY DETECTED_AT DESC LIMIT 15
            """)
            context = context_df.to_string(index=False)
            prompt = (
                "You are FinOps Guardian AI assistant. Answer concisely based on this anomaly data:\n"
                f"{context}\n\n"
                f"Credit rate: ${CREDIT_RATE}/credit.\n"
                f"Question: {user_q}"
            )
            answer = cortex.Complete("mistral-large2", prompt)
            st.markdown(answer)
        except Exception as e:
            st.error(f"AI error: {e}")

    st.divider()
    st.subheader("Demo Controls")

    if st.button("Reset Demo", use_container_width=True):
        session.sql(f"TRUNCATE TABLE {DB}.{SCHEMA}.USAGE_ANOMALIES").collect()
        session.sql(f"TRUNCATE TABLE {DB}.{SCHEMA}.AUDIT_LOG").collect()
        session.sql(f"CALL {DB}.{SCHEMA}.DETECT_IDLE_COMPUTE_DEMO()").collect()
        session.sql(f"CALL {DB}.{SCHEMA}.DETECT_COST_SPIKE_DEMO(2.5)").collect()
        session.sql(f"CALL {DB}.{SCHEMA}.APPLY_FIXES()").collect()
        st.success("Demo reset! 9 auto-resolved + 1 pending approval ready.")
        st.experimental_rerun()

    st.divider()
    st.markdown(f"**Credit Rate:** ${CREDIT_RATE:.2f}/credit")
    st.caption("FinOps Guardian v0.3 | Hackathon Demo")
