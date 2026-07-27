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
CREDIT_RATE = 3.00
KWH_PER_CREDIT = 3.8  # Estimated kWh per Snowflake credit
CO2_PER_KWH = 0.39  # kg CO2 per kWh (US avg grid)


def run_query(sql):
    return session.sql(sql).to_pandas()


# --- Sidebar ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/f/ff/Snowflake_Logo.svg/200px-Snowflake_Logo.svg.png", width=40)
    st.title("FinOps Guardian")
    st.caption("v0.4 | AI-Powered Cost Intelligence")

    st.divider()
    tab_choice = st.radio("Navigation", [
        "Executive Summary",
        "Operations",
        "Intelligence",
        "Compliance",
        "Audit Trail"
    ], label_visibility="collapsed")

    st.divider()
    st.subheader("Agent Controls")
    if st.button("Run Idle Detection", use_container_width=True):
        r = session.sql(f"CALL {DB}.{SCHEMA}.DETECT_IDLE_COMPUTE_DEMO()").collect()
        st.success(r[0][0])
        st.experimental_rerun()
    if st.button("Run Spike Detection", use_container_width=True):
        r = session.sql(f"CALL {DB}.{SCHEMA}.DETECT_COST_SPIKE_DEMO(2.5)").collect()
        st.success(r[0][0])
        st.experimental_rerun()
    if st.button("Apply Fixes", use_container_width=True, type="primary"):
        r = session.sql(f"CALL {DB}.{SCHEMA}.APPLY_FIXES()").collect()
        st.success(r[0][0])
        st.experimental_rerun()
    st.divider()
    if st.button("Reset Demo", use_container_width=True):
        session.sql(f"TRUNCATE TABLE {DB}.{SCHEMA}.USAGE_ANOMALIES").collect()
        session.sql(f"TRUNCATE TABLE {DB}.{SCHEMA}.AUDIT_LOG").collect()
        session.sql(f"CALL {DB}.{SCHEMA}.DETECT_IDLE_COMPUTE_DEMO()").collect()
        session.sql(f"CALL {DB}.{SCHEMA}.DETECT_COST_SPIKE_DEMO(2.5)").collect()
        session.sql(f"CALL {DB}.{SCHEMA}.APPLY_FIXES()").collect()
        st.success("Demo reset!")
        st.experimental_rerun()

# ============================================================
# TAB 1: EXECUTIVE SUMMARY
# ============================================================
if tab_choice == "Executive Summary":
    st.header("Executive Summary")

    # KPI row
    summary = run_query(f"""
        SELECT
            COUNT(*) AS total_anomalies,
            SUM(CREDITS_WASTED) AS total_credits_wasted,
            SUM(CASE WHEN STATUS = 'RESOLVED' THEN CREDITS_WASTED ELSE 0 END) AS credits_saved,
            COUNT(CASE WHEN STATUS IN ('OPEN', 'ACKNOWLEDGED') THEN 1 END) AS open_issues
        FROM {DB}.{SCHEMA}.USAGE_ANOMALIES
    """)
    total_wasted = float(summary["TOTAL_CREDITS_WASTED"].iloc[0] or 0)
    credits_saved = float(summary["CREDITS_SAVED"].iloc[0] or 0)
    dollar_saved = credits_saved * CREDIT_RATE
    co2_saved = credits_saved * KWH_PER_CREDIT * CO2_PER_KWH

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Anomalies", int(summary["TOTAL_ANOMALIES"].iloc[0]))
    c2.metric("Credits Wasted", f"{total_wasted:.2f}")
    c3.metric("$ Saved", f"${dollar_saved:,.2f}")
    c4.metric("Open Issues", int(summary["OPEN_ISSUES"].iloc[0]))
    c5.metric("CO2 Avoided", f"{co2_saved:.1f} kg")

    st.divider()

    # Charts row
    ch1, ch2 = st.columns(2)
    with ch1:
        st.subheader("Savings Trend (7 Days)")
        savings = run_query(f"SELECT SNAPSHOT_DATE, DOLLAR_SAVED FROM {DB}.{SCHEMA}.SAVINGS_HISTORY ORDER BY SNAPSHOT_DATE")
        if not savings.empty:
            st.line_chart(savings.set_index("SNAPSHOT_DATE"))
        else:
            st.info("No savings history yet.")

    with ch2:
        st.subheader("Anomalies by Warehouse")
        chart_data = run_query(f"""
            SELECT WAREHOUSE_NAME, ANOMALY_TYPE, SUM(CREDITS_WASTED) AS CREDITS
            FROM {DB}.{SCHEMA}.USAGE_ANOMALIES GROUP BY 1, 2 ORDER BY CREDITS DESC
        """)
        if not chart_data.empty:
            pivot = chart_data.pivot_table(index="WAREHOUSE_NAME", columns="ANOMALY_TYPE", values="CREDITS", aggfunc="sum").fillna(0)
            st.bar_chart(pivot)

    st.divider()

    # Warehouse Health Scores
    st.subheader("Warehouse Health Scores")

    try:
        session.sql("SHOW WAREHOUSES").collect()
        wh_all = run_query("""
            SELECT "name" AS WH, "state" AS STATE, "size" AS SIZE,
                   "auto_suspend" AS AUTO_SUSPEND, "running" AS RUNNING
            FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
        """)

        if not wh_all.empty:
            anomaly_counts = run_query(f"""
                SELECT WAREHOUSE_NAME, COUNT(*) AS ANOMALY_COUNT
                FROM {DB}.{SCHEMA}.USAGE_ANOMALIES
                WHERE DETECTED_AT >= DATEADD('day', -7, CURRENT_TIMESTAMP())
                GROUP BY WAREHOUSE_NAME
            """)
            anomaly_map = dict(zip(anomaly_counts.get("WAREHOUSE_NAME", []), anomaly_counts.get("ANOMALY_COUNT", [])))

            score_cols = st.columns(min(len(wh_all), 4))
            for i, (_, row) in enumerate(wh_all.iterrows()):
                wh_name = row["WH"]
                auto_sus = int(row["AUTO_SUSPEND"] or 600)
                anomalies = int(anomaly_map.get(wh_name, 0))

                # Health score calculation
                score = 100
                if auto_sus > 300:
                    score -= 15  # Penalty for high auto-suspend
                if auto_sus > 600:
                    score -= 10
                if row["STATE"] == "STARTED" and int(row["RUNNING"] or 0) == 0:
                    score -= 20  # Running but idle right now
                score -= min(anomalies * 8, 40)  # Penalty per recent anomaly
                score = max(score, 0)

                col_idx = i % min(len(wh_all), 4)
                with score_cols[col_idx]:
                    if score >= 80:
                        color = "🟢"
                        label = "Healthy"
                    elif score >= 50:
                        color = "🟡"
                        label = "Needs Attention"
                    else:
                        color = "🔴"
                        label = "Critical"
                    st.metric(f"{color} {wh_name}", f"{score}/100", label)
    except Exception as e:
        st.warning(f"Could not compute health scores: {e}")

    st.divider()

    # Carbon Impact
    st.subheader("Environmental Impact")
    eco1, eco2, eco3 = st.columns(3)
    kwh_saved = credits_saved * KWH_PER_CREDIT
    eco1.metric("Energy Saved", f"{kwh_saved:.1f} kWh")
    eco2.metric("CO2 Avoided", f"{co2_saved:.1f} kg")
    eco3.metric("Equivalent Trees", f"{max(1, int(co2_saved / 21.77))}")
    st.caption("Based on US average grid emissions (0.39 kg CO2/kWh) and ~3.8 kWh per Snowflake credit.")

# ============================================================
# TAB 2: OPERATIONS
# ============================================================
elif tab_choice == "Operations":
    st.header("Operations Center")

    # Pending Approvals
    st.subheader("Pending Approvals")
    pending = run_query(f"""
        SELECT a.ANOMALY_ID, a.WAREHOUSE_NAME, a.ANOMALY_TYPE, a.SEVERITY,
               a.CREDITS_WASTED, a.DESCRIPTION, l.SQL_EXECUTED AS PROPOSED_FIX
        FROM {DB}.{SCHEMA}.USAGE_ANOMALIES a
        JOIN {DB}.{SCHEMA}.AUDIT_LOG l ON l.ANOMALY_ID = a.ANOMALY_ID
        WHERE a.STATUS = 'ACKNOWLEDGED' AND l.STATUS = 'PENDING_APPROVAL'
        ORDER BY a.CREDITS_WASTED DESC
    """)

    if not pending.empty:
        for _, row in pending.iterrows():
            st.markdown("---")
            p1, p2, p3 = st.columns([3, 2, 1])
            with p1:
                dollar_risk = float(row["CREDITS_WASTED"]) * CREDIT_RATE
                st.markdown(f"**{row['WAREHOUSE_NAME']}** | {row['ANOMALY_TYPE']} | **{row['SEVERITY']}**")
                st.text(row["DESCRIPTION"])
                st.caption(f"Credits: {float(row['CREDITS_WASTED']):.2f} | **${dollar_risk:.2f}** at risk")
            with p2:
                st.code(row["PROPOSED_FIX"], language="sql")
            with p3:
                aid = int(row["ANOMALY_ID"])
                if st.button("Approve", key=f"ap_{aid}", type="primary"):
                    session.sql(f"CALL {DB}.{SCHEMA}.APPROVE_FIX({aid}, CURRENT_USER())").collect()
                    st.success("Approved!")
                    st.experimental_rerun()
                if st.button("Dismiss", key=f"dm_{aid}"):
                    session.sql(f"UPDATE {DB}.{SCHEMA}.USAGE_ANOMALIES SET STATUS='DISMISSED' WHERE ANOMALY_ID={aid}").collect()
                    session.sql(f"UPDATE {DB}.{SCHEMA}.AUDIT_LOG SET STATUS='COMPLETED',APPROVED_BY=CURRENT_USER() WHERE ANOMALY_ID={aid} AND STATUS='PENDING_APPROVAL'").collect()
                    st.experimental_rerun()
    else:
        st.success("No pending approvals.")

    st.divider()

    # Warehouse Status
    st.subheader("Warehouse Status (Live)")
    try:
        session.sql("SHOW WAREHOUSES").collect()
        wh_raw = run_query("""
            SELECT "name" AS WAREHOUSE, "state" AS STATUS, "size" AS SIZE,
                   "auto_suspend" AS AUTO_SUSPEND_SEC, "running" AS RUNNING, "queued" AS QUEUED
            FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
        """)
        if not wh_raw.empty:
            wh_raw["STATUS"] = wh_raw["STATUS"].apply(lambda s: "🟢 RUNNING" if s == "STARTED" else "⏸️ SUSPENDED" if s == "SUSPENDED" else s)
            st.dataframe(wh_raw, use_container_width=True)
    except Exception:
        pass

    st.divider()

    # Auto-applied fixes
    st.subheader("Recently Auto-Applied Fixes")
    auto_fixes = run_query(f"""
        SELECT l.LOGGED_AT, l.WAREHOUSE_NAME, a.ANOMALY_TYPE, a.SEVERITY,
               ROUND(a.CREDITS_WASTED * {CREDIT_RATE}, 2) AS DOLLAR_SAVED, l.SQL_EXECUTED
        FROM {DB}.{SCHEMA}.AUDIT_LOG l
        JOIN {DB}.{SCHEMA}.USAGE_ANOMALIES a ON a.ANOMALY_ID = l.ANOMALY_ID
        WHERE l.ACTION_TYPE = 'AUTO_ACTION' AND l.STATUS = 'COMPLETED'
        ORDER BY l.LOGGED_AT DESC LIMIT 15
    """)
    if not auto_fixes.empty:
        st.dataframe(auto_fixes, use_container_width=True)
    else:
        st.info("No auto-applied fixes yet.")

# ============================================================
# TAB 3: INTELLIGENCE
# ============================================================
elif tab_choice == "Intelligence":
    st.header("AI Intelligence")

    # AI Chat
    st.subheader("Ask FinOps Guardian")
    user_q = st.text_input("Ask a question about your Snowflake costs...")
    if user_q:
        try:
            import snowflake.cortex as cortex
            context_df = run_query(f"""
                SELECT WAREHOUSE_NAME, ANOMALY_TYPE, SEVERITY, CREDITS_WASTED, STATUS
                FROM {DB}.{SCHEMA}.USAGE_ANOMALIES ORDER BY DETECTED_AT DESC LIMIT 15
            """)
            prompt = (
                "You are FinOps Guardian, an AI assistant for Snowflake cost optimization. "
                "Answer concisely with specific numbers and actionable recommendations.\n\n"
                f"Current anomaly data:\n{context_df.to_string(index=False)}\n\n"
                f"Credit rate: ${CREDIT_RATE}/credit. "
                f"Total credits saved so far: {context_df[context_df['STATUS']=='RESOLVED']['CREDITS_WASTED'].sum():.2f}\n\n"
                f"Question: {user_q}"
            )
            answer = cortex.Complete("mistral-large2", prompt)
            st.markdown(answer)
        except Exception as e:
            st.error(f"AI error: {e}")

    st.divider()

    # Cost Attribution
    st.subheader("Cost Attribution (Top Users - 7 Days)")
    try:
        attribution = run_query("""
            SELECT USER_NAME, ROLE_NAME, COUNT(*) AS QUERIES,
                   ROUND(SUM(CREDITS_USED_CLOUD_SERVICES), 4) AS CREDITS,
                   ROUND(SUM(CREDITS_USED_CLOUD_SERVICES) * 3.00, 2) AS DOLLARS
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
              AND CREDITS_USED_CLOUD_SERVICES > 0
            GROUP BY USER_NAME, ROLE_NAME ORDER BY CREDITS DESC LIMIT 10
        """)
        if not attribution.empty:
            st.bar_chart(attribution.set_index("USER_NAME")[["DOLLARS"]])
            st.dataframe(attribution, use_container_width=True)
        else:
            st.info("No cost attribution data available.")
    except Exception:
        st.info("Requires ACCOUNT_USAGE access.")

    st.divider()

    # Week-over-Week
    st.subheader("Week-over-Week Comparison")
    try:
        wow = run_query("""
            SELECT WAREHOUSE_NAME,
                   SUM(CASE WHEN START_TIME >= DATE_TRUNC('week', CURRENT_DATE) THEN CREDITS_USED ELSE 0 END) AS THIS_WEEK,
                   SUM(CASE WHEN START_TIME >= DATEADD('week', -1, DATE_TRUNC('week', CURRENT_DATE))
                             AND START_TIME < DATE_TRUNC('week', CURRENT_DATE) THEN CREDITS_USED ELSE 0 END) AS LAST_WEEK
            FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
            WHERE START_TIME >= DATEADD('week', -2, CURRENT_DATE)
              AND WAREHOUSE_NAME != 'CLOUD_SERVICES_ONLY'
            GROUP BY WAREHOUSE_NAME HAVING THIS_WEEK > 0 OR LAST_WEEK > 0
        """)
        if not wow.empty:
            wcols = st.columns(min(len(wow), 4))
            for i, (_, row) in enumerate(wow.iterrows()):
                tw = float(row["THIS_WEEK"] or 0)
                lw = float(row["LAST_WEEK"] or 0)
                delta = f"{((tw-lw)/lw*100):+.1f}%" if lw > 0 else "new"
                with wcols[i % min(len(wow), 4)]:
                    st.metric(row["WAREHOUSE_NAME"], f"{tw:.2f}", delta)
        else:
            st.info("Not enough data for comparison.")
    except Exception:
        st.info("Requires ACCOUNT_USAGE access.")

# ============================================================
# TAB 4: COMPLIANCE
# ============================================================
elif tab_choice == "Compliance":
    st.header("Policy Compliance")
    st.caption("Checking warehouse configurations against FinOps best practices.")

    try:
        session.sql("SHOW WAREHOUSES").collect()
        wh_data = run_query("""
            SELECT "name" AS WH, "size" AS SIZE, "auto_suspend" AS AUTO_SUSPEND,
                   "auto_resume" AS AUTO_RESUME, "type" AS TYPE
            FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
        """)

        if not wh_data.empty:
            total_checks = 0
            passed_checks = 0
            findings = []

            for _, wh in wh_data.iterrows():
                name = wh["WH"]
                auto_sus = int(wh["AUTO_SUSPEND"] or 0)
                size = wh["SIZE"]

                # Check 1: Auto-suspend should be <= 300s (5 min)
                total_checks += 1
                if auto_sus <= 300:
                    passed_checks += 1
                else:
                    severity = "HIGH" if auto_sus > 600 else "MEDIUM"
                    findings.append({
                        "Warehouse": name,
                        "Check": "Auto-Suspend Timeout",
                        "Status": "FAIL",
                        "Severity": severity,
                        "Current": f"{auto_sus}s",
                        "Recommended": "60-300s",
                        "Fix": f"ALTER WAREHOUSE {name} SET AUTO_SUSPEND = 60;"
                    })

                # Check 2: Auto-resume should be enabled
                total_checks += 1
                if str(wh["AUTO_RESUME"]).lower() == "true":
                    passed_checks += 1
                else:
                    findings.append({
                        "Warehouse": name,
                        "Check": "Auto-Resume Disabled",
                        "Status": "FAIL",
                        "Severity": "LOW",
                        "Current": "false",
                        "Recommended": "true",
                        "Fix": f"ALTER WAREHOUSE {name} SET AUTO_RESUME = TRUE;"
                    })

                # Check 3: Size appropriateness (flag X-Large+ for non-ETL)
                total_checks += 1
                large_sizes = ["Large", "X-Large", "2X-Large", "3X-Large", "4X-Large"]
                if size in large_sizes and "ETL" not in name.upper():
                    findings.append({
                        "Warehouse": name,
                        "Check": "Potentially Oversized",
                        "Status": "WARN",
                        "Severity": "MEDIUM",
                        "Current": size,
                        "Recommended": "Review utilization",
                        "Fix": f"-- Review WAREHOUSE_LOAD_HISTORY for {name}"
                    })
                else:
                    passed_checks += 1

            # Compliance Score
            compliance_pct = int((passed_checks / total_checks) * 100) if total_checks > 0 else 100

            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Compliance Score", f"{compliance_pct}%")
            sc2.metric("Checks Passed", f"{passed_checks}/{total_checks}")
            sc3.metric("Issues Found", len(findings))

            st.divider()

            if findings:
                st.subheader("Policy Violations")
                for f in findings:
                    with st.expander(f"{f['Severity']} | {f['Warehouse']} - {f['Check']}"):
                        fc1, fc2 = st.columns(2)
                        with fc1:
                            st.markdown(f"**Current value:** `{f['Current']}`")
                            st.markdown(f"**Recommended:** `{f['Recommended']}`")
                        with fc2:
                            st.code(f["Fix"], language="sql")
            else:
                st.success("All warehouses comply with best practices!")

            st.divider()
            st.subheader("Best Practice Reference")
            st.markdown("""
| Policy | Recommended | Why |
|--------|------------|-----|
| Auto-Suspend | 60-300 seconds | Prevents idle compute charges |
| Auto-Resume | Enabled | Ensures availability on demand |
| Warehouse Size | Match workload | Avoid paying for unused capacity |
| Resource Monitor | Configured | Prevents runaway spending |
| Statement Timeout | Set (1-4 hours) | Kills runaway queries |
""")
    except Exception as e:
        st.error(f"Could not run compliance checks: {e}")

# ============================================================
# TAB 5: AUDIT TRAIL
# ============================================================
elif tab_choice == "Audit Trail":
    st.header("Audit Trail")

    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        warehouses = run_query(f"""
            SELECT DISTINCT WAREHOUSE_NAME FROM {DB}.{SCHEMA}.AUDIT_LOG
            WHERE WAREHOUSE_NAME IS NOT NULL ORDER BY 1
        """)
        wh_options = ["All"] + warehouses["WAREHOUSE_NAME"].tolist()
        wh_filter = st.selectbox("Warehouse", wh_options)
    with fcol2:
        status_filter = st.selectbox("Status", ["All", "COMPLETED", "PENDING_APPROVAL", "FAILED"])
    with fcol3:
        action_filter = st.selectbox("Action Type", ["All", "DETECTION", "AUTO_ACTION", "RECOMMENDATION", "USER_ACTION"])

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
