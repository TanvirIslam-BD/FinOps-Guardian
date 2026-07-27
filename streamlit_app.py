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
    st.markdown("""
    <div style="text-align:center;padding:10px 0 5px 0;">
        <span style="font-size:2.2rem;">🛡️</span>
        <h2 style="margin:0;padding:4px 0 0 0;">FinOps Guardian</h2>
        <p style="margin:0;color:#888;font-size:0.82rem;">AI-Powered Cost Intelligence</p>
    </div>
    """, unsafe_allow_html=True)

    # Quick status summary
    notif_count = run_query(f"SELECT COUNT(*) AS CNT FROM {DB}.{SCHEMA}.NOTIFICATIONS WHERE IS_READ = FALSE")
    unread = int(notif_count["CNT"].iloc[0])

    open_count = run_query(f"SELECT COUNT(*) AS CNT FROM {DB}.{SCHEMA}.USAGE_ANOMALIES WHERE STATUS IN ('OPEN','ACKNOWLEDGED')")
    open_issues = int(open_count["CNT"].iloc[0])

    st.markdown("")
    s1, s2 = st.columns(2)
    s1.metric("Open Issues", open_issues)
    s2.metric("Unread", unread)

    st.markdown("")
    st.markdown("**Navigate**")
    notif_label = f"🔔 Notifications ({unread})" if unread > 0 else "🔔 Notifications"
    tab_choice = st.radio("Navigation", [
        "📊 Executive Summary",
        "⚙️ Operations",
        "🧠 Intelligence",
        "📋 Compliance",
        notif_label,
        "📜 Audit Trail"
    ], label_visibility="collapsed")

    st.markdown("")
    st.markdown("**Agent Controls**")
    st.caption("Run AI detection scans and apply fixes")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔍 Idle Scan", use_container_width=True):
            r = session.sql(f"CALL {DB}.{SCHEMA}.DETECT_IDLE_COMPUTE_DEMO()").collect()
            st.success(r[0][0])
            st.experimental_rerun()
    with col_b:
        if st.button("📈 Spike Scan", use_container_width=True):
            r = session.sql(f"CALL {DB}.{SCHEMA}.DETECT_COST_SPIKE_DEMO(2.5)").collect()
            st.success(r[0][0])
            st.experimental_rerun()
    if st.button("⚡ Apply Fixes", use_container_width=True, type="primary"):
        r = session.sql(f"CALL {DB}.{SCHEMA}.APPLY_FIXES()").collect()
        st.success(r[0][0])
        st.experimental_rerun()

    st.markdown("")
    with st.expander("🔄 Reset Demo"):
        st.caption("Clears all data and re-runs detection pipeline")
        if st.button("Reset All Data", use_container_width=True):
            session.sql(f"TRUNCATE TABLE {DB}.{SCHEMA}.USAGE_ANOMALIES").collect()
            session.sql(f"TRUNCATE TABLE {DB}.{SCHEMA}.AUDIT_LOG").collect()
            session.sql(f"TRUNCATE TABLE {DB}.{SCHEMA}.NOTIFICATIONS").collect()
            session.sql(f"CALL {DB}.{SCHEMA}.DETECT_IDLE_COMPUTE_DEMO()").collect()
            session.sql(f"CALL {DB}.{SCHEMA}.DETECT_COST_SPIKE_DEMO(2.5)").collect()
            session.sql(f"CALL {DB}.{SCHEMA}.APPLY_FIXES()").collect()
            st.success("Demo reset complete!")
            st.experimental_rerun()

    st.markdown("")
    st.markdown("""<p style="text-align:center;color:#666;font-size:0.72rem;margin-top:10px;">
    v0.5 | Built with Snowflake Cortex AI
    </p>""", unsafe_allow_html=True)

# ============================================================
# TAB 1: EXECUTIVE SUMMARY
# ============================================================
if "Executive Summary" in tab_choice:
    st.header("📊 Executive Summary")
    st.caption("Real-time overview of your Snowflake cost optimization posture")

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
    c1.metric("🚨 Anomalies", int(summary["TOTAL_ANOMALIES"].iloc[0]))
    c2.metric("💸 Credits Wasted", f"{total_wasted:.2f}")
    c3.metric("💰 $ Saved", f"${dollar_saved:,.2f}")
    c4.metric("⚠️ Open Issues", int(summary["OPEN_ISSUES"].iloc[0]))
    c5.metric("🌱 CO2 Avoided", f"{co2_saved:.1f} kg")

    st.markdown("")

    # Charts row
    ch1, ch2 = st.columns(2)
    with ch1:
        st.subheader("Savings Trend (7 Days)")
        savings = run_query(f"SELECT SNAPSHOT_DATE, DOLLAR_SAVED FROM {DB}.{SCHEMA}.SAVINGS_HISTORY ORDER BY SNAPSHOT_DATE")
        if not savings.empty:
            st.line_chart(savings.set_index("SNAPSHOT_DATE"))
        else:
            st.info("No savings history yet. Run detection + apply fixes to populate.")

    with ch2:
        st.subheader("Anomalies by Warehouse")
        chart_data = run_query(f"""
            SELECT WAREHOUSE_NAME, ANOMALY_TYPE, SUM(CREDITS_WASTED) AS CREDITS
            FROM {DB}.{SCHEMA}.USAGE_ANOMALIES GROUP BY 1, 2 ORDER BY CREDITS DESC
        """)
        if not chart_data.empty:
            pivot = chart_data.pivot_table(index="WAREHOUSE_NAME", columns="ANOMALY_TYPE", values="CREDITS", aggfunc="sum").fillna(0)
            st.bar_chart(pivot)

    st.markdown("")

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
    st.subheader("🌍 Environmental Impact")
    eco1, eco2, eco3 = st.columns(3)
    kwh_saved = credits_saved * KWH_PER_CREDIT
    eco1.metric("⚡ Energy Saved", f"{kwh_saved:.1f} kWh")
    eco2.metric("🌱 CO2 Avoided", f"{co2_saved:.1f} kg")
    eco3.metric("🌳 Equivalent Trees", f"{max(1, int(co2_saved / 21.77))}")
    st.caption("Based on US average grid emissions (0.39 kg CO2/kWh) and ~3.8 kWh per Snowflake credit.")

# ============================================================
# TAB 2: OPERATIONS
# ============================================================
elif "Operations" in tab_choice:
    st.header("⚙️ Operations Center")
    st.caption("Manage approvals, view warehouse status, and track automated fixes")

    # Pending Approvals
    st.subheader("🔐 Pending Approvals")
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

    st.markdown("")

    # Warehouse Status
    st.subheader("🖥️ Warehouse Status (Live)")
    try:
        session.sql("SHOW WAREHOUSES").collect()
        wh_raw = run_query("""
            SELECT "name" AS WAREHOUSE, "state" AS STATUS, "size" AS SIZE,
                   "auto_suspend" AS AUTO_SUSPEND_SEC, "running" AS RUNNING, "queued" AS QUEUED
            FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
        """)
        if not wh_raw.empty:
            wh_raw["STATUS"] = wh_raw["STATUS"].apply(lambda s: "🟢 RUNNING" if s == "STARTED" else "⏸️ SUSPENDED" if s == "SUSPENDED" else s)
            for _, wrow in wh_raw.iterrows():
                wcol1, wcol2, wcol3, wcol4 = st.columns([3, 2, 2, 2])
                wcol1.markdown(f"**{wrow['WAREHOUSE']}**")
                wcol2.markdown(f"{wrow['STATUS']}")
                wcol3.markdown(f"Size: `{wrow['SIZE']}`")
                wcol4.markdown(f"Suspend: `{wrow['AUTO_SUSPEND_SEC']}s`")
    except Exception:
        pass

    st.markdown("")

    # Auto-applied fixes
    st.subheader("🤖 Recently Auto-Applied Fixes")
    auto_fixes = run_query(f"""
        SELECT l.LOGGED_AT, l.WAREHOUSE_NAME, a.ANOMALY_TYPE, a.SEVERITY,
               ROUND(a.CREDITS_WASTED * {CREDIT_RATE}, 2) AS DOLLAR_SAVED, l.SQL_EXECUTED
        FROM {DB}.{SCHEMA}.AUDIT_LOG l
        JOIN {DB}.{SCHEMA}.USAGE_ANOMALIES a ON a.ANOMALY_ID = l.ANOMALY_ID
        WHERE l.ACTION_TYPE = 'AUTO_ACTION' AND l.STATUS = 'COMPLETED'
        ORDER BY l.LOGGED_AT DESC LIMIT 10
    """)
    if not auto_fixes.empty:
        for _, fix in auto_fixes.iterrows():
            with st.expander(f"{fix['SEVERITY']} | {fix['WAREHOUSE_NAME']} — ${fix['DOLLAR_SAVED']} saved"):
                st.markdown(f"**Type:** {fix['ANOMALY_TYPE']} | **When:** {fix['LOGGED_AT']}")
                st.code(fix["SQL_EXECUTED"], language="sql")
    else:
        st.info("No auto-applied fixes yet. Run detection + Apply Fixes to see results.")

# ============================================================
# TAB 3: INTELLIGENCE
# ============================================================
elif "Intelligence" in tab_choice:
    st.header("🧠 AI Intelligence")
    st.caption("AI-powered insights and cost attribution analysis")

    # AI Chat
    st.subheader("💬 Ask FinOps Guardian")
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

    st.markdown("")

    # Cost Attribution
    st.subheader("👥 Cost Attribution (Top Users - 7 Days)")
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

    st.markdown("")

    # Week-over-Week
    st.subheader("📈 Week-over-Week Comparison")
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
elif "Compliance" in tab_choice:
    st.header("📋 Policy Compliance")
    st.caption("Automated checks against FinOps best practices")

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
            score_icon = "✅" if compliance_pct >= 80 else "⚠️" if compliance_pct >= 50 else "❌"
            sc1.metric(f"{score_icon} Compliance Score", f"{compliance_pct}%")
            sc2.metric("✔️ Checks Passed", f"{passed_checks}/{total_checks}")
            sc3.metric("🔍 Issues Found", len(findings))

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
# TAB 5: NOTIFICATIONS
# ============================================================
elif "Notifications" in tab_choice:
    st.header("🔔 Notifications")
    st.caption("Activity feed for approvals, alerts, and system events")

    # Unread count
    notifs = run_query(f"""
        SELECT NOTIFICATION_ID, CREATED_AT, NOTIFICATION_TYPE, TITLE, MESSAGE,
               WAREHOUSE_NAME, IS_READ
        FROM {DB}.{SCHEMA}.NOTIFICATIONS
        ORDER BY CREATED_AT DESC
        LIMIT 30
    """)

    unread_notifs = notifs[notifs["IS_READ"] == False] if not notifs.empty else notifs
    read_notifs = notifs[notifs["IS_READ"] == True] if not notifs.empty else notifs

    # Mark all as read button
    n1, n2 = st.columns([3, 1])
    with n1:
        st.markdown(f"**{len(unread_notifs)}** unread notifications")
    with n2:
        if st.button("✓ Mark all read", use_container_width=True):
            session.sql(f"UPDATE {DB}.{SCHEMA}.NOTIFICATIONS SET IS_READ = TRUE WHERE IS_READ = FALSE").collect()
            st.experimental_rerun()

    st.divider()

    if notifs.empty:
        st.info("No notifications yet. Run detection scans and apply fixes to generate notifications.")
    else:
        # Unread section
        if not unread_notifs.empty:
            st.subheader("Unread")
            for _, n in unread_notifs.iterrows():
                ntype = n["NOTIFICATION_TYPE"]
                if ntype == "APPROVAL_NEEDED":
                    icon = "🔴"
                elif ntype == "APPROVED":
                    icon = "🟢"
                else:
                    icon = "🔵"

                st.markdown(f"""
**{icon} {n['TITLE']}**
{n['MESSAGE']}
<small style="color: #888;">{n['CREATED_AT']} | {n['WAREHOUSE_NAME']}</small>
""", unsafe_allow_html=True)
                st.markdown("---")

        # Read section
        if not read_notifs.empty:
            with st.expander(f"Earlier ({len(read_notifs)} read)"):
                for _, n in read_notifs.iterrows():
                    ntype = n["NOTIFICATION_TYPE"]
                    if ntype == "APPROVAL_NEEDED":
                        icon = "🔴"
                    elif ntype == "APPROVED":
                        icon = "🟢"
                    else:
                        icon = "🔵"
                    st.markdown(f"**{icon} {n['TITLE']}** - {n['MESSAGE']}")

# ============================================================
# TAB 6: AUDIT TRAIL
# ============================================================
elif "Audit Trail" in tab_choice:
    st.header("📜 Audit Trail")
    st.caption("Complete history of all detections, actions, and approvals")

    # Summary stats
    audit_stats = run_query(f"""
        SELECT
            COUNT(*) AS TOTAL_ENTRIES,
            COUNT(CASE WHEN ACTION_TYPE = 'AUTO_ACTION' THEN 1 END) AS AUTO_ACTIONS,
            COUNT(CASE WHEN ACTION_TYPE = 'USER_ACTION' THEN 1 END) AS MANUAL_ACTIONS,
            COUNT(CASE WHEN STATUS = 'PENDING_APPROVAL' THEN 1 END) AS PENDING
        FROM {DB}.{SCHEMA}.AUDIT_LOG
    """)
    as1, as2, as3, as4 = st.columns(4)
    as1.metric("Total Entries", int(audit_stats["TOTAL_ENTRIES"].iloc[0]))
    as2.metric("🤖 Auto Actions", int(audit_stats["AUTO_ACTIONS"].iloc[0]))
    as3.metric("👤 Manual Actions", int(audit_stats["MANUAL_ACTIONS"].iloc[0]))
    as4.metric("⏳ Pending", int(audit_stats["PENDING"].iloc[0]))

    st.markdown("")

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

    if not audit_log.empty:
        for _, entry in audit_log.iterrows():
            action = entry["ACTION_TYPE"]
            if action == "AUTO_ACTION":
                icon = "🤖"
            elif action == "USER_ACTION":
                icon = "👤"
            elif action == "RECOMMENDATION":
                icon = "💡"
            else:
                icon = "🔍"

            status = entry["STATUS"]
            if status == "COMPLETED":
                status_badge = "✅"
            elif status == "PENDING_APPROVAL":
                status_badge = "⏳"
            else:
                status_badge = "❌"

            with st.expander(f"{icon} {entry['ACTION_TYPE']} | {entry['WAREHOUSE_NAME']} | {status_badge} {status} — {entry['LOGGED_AT']}"):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**Anomaly ID:** {entry['ANOMALY_ID']}")
                    st.markdown(f"**Details:** {entry['ACTION_DETAILS']}")
                    if entry["APPROVED_BY"]:
                        st.markdown(f"**Approved by:** {entry['APPROVED_BY']}")
                with col_b:
                    if entry["SQL_EXECUTED"]:
                        st.code(entry["SQL_EXECUTED"], language="sql")
    else:
        st.info("No audit entries match your filters.")
