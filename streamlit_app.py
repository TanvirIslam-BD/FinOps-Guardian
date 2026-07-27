import streamlit as st
from snowflake.snowpark.context import get_active_session
from datetime import datetime, timedelta

st.set_page_config(
    page_title="FinOps Guardian",
    page_icon="🛡️",
    layout="wide",
)

# --- Custom CSS for Reference Design ---
st.markdown("""
<style>
/* Hide default Streamlit padding and header */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 1rem !important;
}
header[data-testid="stHeader"] {
    display: none;
}

/* Sidebar styling */
[data-testid="stSidebar"] {
    background: #FFFFFF;
    border-right: 1px solid #E8ECF0;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 0rem;
}
[data-testid="stSidebar"] .block-container,
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    padding-top: 0 !important;
    margin-top: 0 !important;
}
[data-testid="stSidebar"] > div > div:first-child {
    padding-top: 0 !important;
}

/* Radio buttons as nav items - styled with active/inactive states */
[data-testid="stSidebar"] .stRadio > div {
    gap: 2px !important;
}
[data-testid="stSidebar"] .stRadio > div > label {
    padding: 11px 16px !important;
    margin: 0 !important;
    border-radius: 8px !important;
    border-left: 3px solid transparent !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    font-size: 0.88rem !important;
    color: #6B7280 !important;
    font-weight: 400 !important;
    background: transparent !important;
    cursor: pointer;
    width: 100% !important;
    display: block !important;
    box-sizing: border-box !important;
}
[data-testid="stSidebar"] .stRadio > div > label > div:first-child {
    display: none !important;
}
[data-testid="stSidebar"] .stRadio > div > label:hover {
    background: rgba(102, 126, 234, 0.06) !important;
    color: #4B5563 !important;
    border-left: 3px solid rgba(102, 126, 234, 0.3) !important;
}

/* Button styling */
.stButton > button {
    border-radius: 8px;
    font-weight: 500;
    font-size: 0.85rem;
    transition: all 0.2s;
    border: 1px solid #E5E7EB;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
    box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 14px rgba(102, 126, 234, 0.4);
}

/* Expander styling */
.streamlit-expanderHeader {
    font-size: 0.88rem;
    font-weight: 500;
    border-radius: 8px;
}

/* Selectbox */
[data-testid="stSelectbox"] > div > div {
    border-radius: 8px;
    font-size: 0.85rem;
}

/* Smooth content transitions */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}
.main .block-container > div {
    animation: fadeIn 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Metric override */
[data-testid="stMetricValue"] {
    font-size: 1.4rem !important;
}

/* Scrollbar styling */
[data-testid="stSidebar"] ::-webkit-scrollbar {
    width: 4px;
}
[data-testid="stSidebar"] ::-webkit-scrollbar-thumb {
    background: #D1D5DB;
    border-radius: 4px;
}
[data-testid="stSidebar"] ::-webkit-scrollbar-track {
    background: transparent;
}

/* KPI card hover */
.kpi-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Spinner override */
[data-testid="stSpinner"] > div {
    border-color: #667eea transparent transparent transparent !important;
}
</style>
""", unsafe_allow_html=True)

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
KWH_PER_CREDIT = 3.8
CO2_PER_KWH = 0.39


def run_query(sql):
    return session.sql(sql).to_pandas()


# --- Helper Functions for Reference UI Components ---

def render_kpi_card(icon_emoji, icon_bg, label, value, delta_text="", delta_positive=True):
    """Render a KPI card matching the reference design."""
    delta_color = "#16A34A" if delta_positive else "#DC2626"
    delta_arrow = "↑" if delta_positive else "↓"
    delta_html = f'<div style="font-size:0.75rem;color:{delta_color};margin-top:4px;">{delta_arrow} {delta_text}</div>' if delta_text else ""
    return f"""
    <div class="kpi-card" style="background:#fff;border:1px solid #E8ECF0;border-radius:12px;padding:16px 18px;height:100%;transition:all 0.2s ease;">
        <div style="width:36px;height:36px;background:{icon_bg};border-radius:10px;display:flex;align-items:center;justify-content:center;margin-bottom:10px;">
            <span style="font-size:1rem;">{icon_emoji}</span>
        </div>
        <div style="font-size:0.7rem;color:#888;text-transform:uppercase;letter-spacing:0.5px;font-weight:500;">{label}</div>
        <div style="font-size:1.5rem;font-weight:700;color:#1a1a2e;margin-top:2px;">{value}</div>
        {delta_html}
    </div>"""


def render_chart_card(title, chart_placeholder_id=""):
    """Render opening HTML for a chart card container."""
    return f"""
    <div style="background:#fff;border:1px solid #E8ECF0;border-radius:12px;padding:20px;margin-bottom:16px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
            <div style="display:flex;align-items:center;gap:8px;">
                <span style="font-size:0.95rem;font-weight:600;color:#1a1a2e;">{title}</span>
                <span style="color:#aaa;font-size:0.8rem;">ℹ️</span>
            </div>
            <div style="display:flex;gap:8px;">
                <span style="background:#F3F4F6;padding:4px 10px;border-radius:6px;font-size:0.75rem;color:#555;">USD</span>
                <span style="background:#F3F4F6;padding:4px 10px;border-radius:6px;font-size:0.75rem;color:#555;">Last 7 Days</span>
            </div>
        </div>
    </div>"""


def render_health_card(name, score, state="STARTED"):
    """Render a warehouse health card with progress bar."""
    if score >= 80:
        color = "#16A34A"
        badge_bg = "rgba(22,163,74,0.1)"
        label = "Healthy"
        dot = "🟢"
    elif score >= 50:
        color = "#F59E0B"
        badge_bg = "rgba(245,158,11,0.1)"
        label = "Needs Attention"
        dot = "🟡"
    else:
        color = "#DC2626"
        badge_bg = "rgba(220,38,38,0.1)"
        label = "Critical"
        dot = "🔴"

    return f"""
    <div style="background:#fff;border:1px solid #E8ECF0;border-radius:12px;padding:16px 18px;margin-bottom:8px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
            <div style="display:flex;align-items:center;gap:8px;">
                <span style="font-size:0.7rem;">{dot}</span>
                <span style="font-weight:600;color:#1a1a2e;font-size:0.95rem;">{name}</span>
            </div>
            <span style="background:{badge_bg};color:{color};padding:3px 10px;border-radius:6px;font-size:0.75rem;font-weight:500;">{label}</span>
        </div>
        <div style="font-size:1.4rem;font-weight:700;color:#1a1a2e;margin-bottom:8px;">{score}/100</div>
        <div style="background:#F3F4F6;border-radius:6px;height:8px;overflow:hidden;">
            <div style="background:{color};height:100%;width:{score}%;border-radius:6px;transition:width 0.5s;"></div>
        </div>
        <div style="font-size:0.72rem;color:#16A34A;margin-top:6px;">↑ vs last 7 days</div>
    </div>"""


# --- Sidebar ---
if "nav_index" not in st.session_state:
    st.session_state.nav_index = 0

with st.sidebar:
    # Logo + Name inline
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;padding:0 4px 12px 4px;">
        <div style="width:38px;height:38px;min-width:38px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);border-radius:10px;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(102,126,234,0.3);">
            <span style="font-size:1.2rem;line-height:38px;">🛡️</span>
        </div>
        <div>
            <div style="font-size:1.05rem;font-weight:700;background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent;line-height:1.2;">FinOps Guardian</div>
            <div style="font-size:0.65rem;color:#999;letter-spacing:0.3px;">Expense Intelligence ✨</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Quick Stats
    notif_count = run_query(f"SELECT COUNT(*) AS CNT FROM {DB}.{SCHEMA}.NOTIFICATIONS WHERE IS_READ = FALSE")
    unread = int(notif_count["CNT"].iloc[0])

    open_count = run_query(f"SELECT COUNT(*) AS CNT FROM {DB}.{SCHEMA}.USAGE_ANOMALIES WHERE STATUS IN ('OPEN','ACKNOWLEDGED')")
    open_issues = int(open_count["CNT"].iloc[0])

    wh_count = run_query("SHOW WAREHOUSES")
    servers = len(wh_count) if not wh_count.empty else 3

    st.markdown("""<div style="font-size:0.68rem;color:#999;text-transform:uppercase;letter-spacing:1.2px;margin:4px 0 8px 0;font-weight:600;">Quick Stats</div>""", unsafe_allow_html=True)
    st.markdown(f"""
    <div style="display:flex;gap:8px;margin:0 0 12px 0;">
        <div style="flex:1;background:rgba(102,126,234,0.04);border:1px solid rgba(102,126,234,0.12);border-radius:10px;padding:10px 12px;text-align:center;">
            <div style="font-size:1.4rem;font-weight:700;color:#DC2626;margin-bottom:2px;">🖥 {servers}</div>
            <div style="font-size:0.65rem;color:#888;font-weight:500;">Servers</div>
        </div>
        <div style="flex:1;background:rgba(102,126,234,0.04);border:1px solid rgba(102,126,234,0.12);border-radius:10px;padding:10px 12px;text-align:center;">
            <div style="font-size:1.4rem;font-weight:700;color:#667eea;margin-bottom:2px;">👥 {unread}</div>
            <div style="font-size:0.65rem;color:#888;font-weight:500;">Users</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # View Notifications link
    if unread > 0:
        if st.button(f"View {unread} Notifications →", use_container_width=True, key="notif_badge"):
            st.session_state.nav_index = 5
            st.experimental_rerun()

    # Navigation
    st.markdown("""<div style="font-size:0.68rem;color:#999;text-transform:uppercase;letter-spacing:1.2px;margin:18px 0 6px 0;font-weight:600;">Navigation</div>""", unsafe_allow_html=True)
    notif_label = f"🔔 Notifications ({unread})" if unread > 0 else "🔔 Notifications"
    nav_options = [
        "📊 Executive Summary",
        "⚙️ Operations",
        "✅ Approvals",
        "🧠 Intelligence",
        "📋 Compliance",
        notif_label,
        "📜 Audit Trail"
    ]

    tab_choice = st.radio("Navigation", nav_options,
        index=st.session_state.nav_index, label_visibility="collapsed")

    current_idx = nav_options.index(tab_choice) if tab_choice in nav_options else 0
    if current_idx != st.session_state.nav_index:
        st.session_state.nav_index = current_idx

    # Inject dynamic CSS to highlight the active nav item by nth-child
    active_nth = st.session_state.nav_index + 1
    st.markdown(f"""<style>
    [data-testid="stSidebar"] .stRadio > div > label:nth-child({active_nth}) {{
        border-left: 3px solid #667eea !important;
        background: linear-gradient(90deg, rgba(102,126,234,0.12) 0%, rgba(102,126,234,0.03) 100%) !important;
        color: #4338CA !important;
        font-weight: 600 !important;
        box-shadow: 0 1px 3px rgba(102,126,234,0.08) !important;
    }}
    </style>""", unsafe_allow_html=True)

    # Quick Actions
    st.markdown("""<div style="font-size:0.68rem;color:#999;text-transform:uppercase;letter-spacing:1.2px;margin:22px 0 6px 0;font-weight:600;">Quick Actions</div>""", unsafe_allow_html=True)
    st.caption("Shortcuts for common tasks")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📤 Upload Scan", use_container_width=True):
            r = session.sql(f"CALL {DB}.{SCHEMA}.DETECT_IDLE_COMPUTE_DEMO()").collect()
            st.success(r[0][0])
            st.experimental_rerun()
    with col_b:
        if st.button("📋 Explorer", use_container_width=True):
            r = session.sql(f"CALL {DB}.{SCHEMA}.DETECT_COST_SPIKE_DEMO(2.5)").collect()
            st.success(r[0][0])
            st.experimental_rerun()
    if st.button("+ New Scan", use_container_width=True, type="primary"):
        r = session.sql(f"CALL {DB}.{SCHEMA}.APPLY_FIXES()").collect()
        st.success(r[0][0])
        st.experimental_rerun()

    st.selectbox("Scan Profile", ["Default", "Cost Optimization", "Idle Detection", "Full Audit"], label_visibility="visible")

    with st.expander("🔄 Reset Demo"):
        st.caption("Clears all data and re-runs full pipeline")
        if st.button("Reset All Data", use_container_width=True):
            session.sql(f"TRUNCATE TABLE {DB}.{SCHEMA}.USAGE_ANOMALIES").collect()
            session.sql(f"TRUNCATE TABLE {DB}.{SCHEMA}.AUDIT_LOG").collect()
            session.sql(f"TRUNCATE TABLE {DB}.{SCHEMA}.NOTIFICATIONS").collect()
            session.sql(f"CALL {DB}.{SCHEMA}.DETECT_IDLE_COMPUTE_DEMO()").collect()
            session.sql(f"CALL {DB}.{SCHEMA}.DETECT_COST_SPIKE_DEMO(2.5)").collect()
            session.sql(f"CALL {DB}.{SCHEMA}.APPLY_FIXES()").collect()
            st.success("Demo reset complete!")
            st.experimental_rerun()

    # Footer
    st.markdown("""
    <div style="text-align:center;margin-top:24px;padding-top:12px;border-top:1px solid #E8ECF0;">
        <p style="color:#888;font-size:0.68rem;margin:0;">© 2025 FinOps Guardian</p>
        <p style="color:#bbb;font-size:0.6rem;margin:2px 0 0 0;">All rights reserved</p>
    </div>
    """, unsafe_allow_html=True)


# --- Page Header ---
def render_page_header(title, emoji):
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    date_range = f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}"

    st.markdown(f"""
    <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid #E8ECF0;">
        <div>
            <h1 style="margin:0;font-size:1.6rem;color:#1a1a2e;">{emoji} {title}</h1>
            <p style="margin:4px 0 0 0;color:#888;font-size:0.82rem;">Monitor your app health, usage and key metrics at a glance</p>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
            <span style="background:#F3F4F6;padding:8px 16px;border-radius:8px;font-size:0.82rem;color:#555;border:1px solid #E5E7EB;cursor:pointer;">📅 {date_range} ▾</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# TAB 1: EXECUTIVE SUMMARY
# ============================================================
if "Executive Summary" in tab_choice:
    render_page_header("Executive Summary", "📊")

    # Fetch data
    summary = run_query(f"""
        SELECT
            COUNT(*) AS total_anomalies,
            SUM(CREDITS_WASTED) AS total_credits_wasted,
            SUM(CASE WHEN STATUS = 'RESOLVED' THEN CREDITS_WASTED ELSE 0 END) AS credits_saved,
            COUNT(CASE WHEN STATUS IN ('OPEN', 'ACKNOWLEDGED') THEN 1 END) AS open_issues
        FROM {DB}.{SCHEMA}.USAGE_ANOMALIES
    """)
    total_anomalies = int(summary["TOTAL_ANOMALIES"].iloc[0])
    total_wasted = float(summary["TOTAL_CREDITS_WASTED"].iloc[0] or 0)
    credits_saved = float(summary["CREDITS_SAVED"].iloc[0] or 0)
    dollar_saved = credits_saved * CREDIT_RATE
    open_iss = int(summary["OPEN_ISSUES"].iloc[0])
    co2_saved = credits_saved * KWH_PER_CREDIT * CO2_PER_KWH

    # KPI Cards row
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(render_kpi_card("🚨", "rgba(220,38,38,0.1)", "Anomalies Detected", str(total_anomalies), "2 vs last 7 days", True), unsafe_allow_html=True)
    with c2:
        st.markdown(render_kpi_card("💰", "rgba(245,158,11,0.1)", "Credits Wasted", f"{total_wasted:.2f}", f"{total_wasted:.1f} credits", False), unsafe_allow_html=True)
    with c3:
        st.markdown(render_kpi_card("💵", "rgba(22,163,74,0.1)", "Dollars Saved", f"${dollar_saved:,.2f}", f"${dollar_saved:.0f} recovered", True), unsafe_allow_html=True)
    with c4:
        st.markdown(render_kpi_card("📋", "rgba(59,130,246,0.1)", "Open Issues", str(open_iss), f"{open_iss} pending", open_iss == 0), unsafe_allow_html=True)
    with c5:
        st.markdown(render_kpi_card("🌱", "rgba(22,163,74,0.1)", "CO2 Avoided", f"{co2_saved:.1f} kg", f"{co2_saved:.1f} kg saved", True), unsafe_allow_html=True)

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

    # Charts row in card containers
    ch1, ch2 = st.columns(2)
    with ch1:
        st.markdown("""<div style="background:#fff;border:1px solid #E8ECF0;border-radius:12px;padding:20px;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
                <span style="font-size:0.95rem;font-weight:600;color:#1a1a2e;">Savings Trend (7 Days)</span>
                <div style="display:flex;gap:6px;">
                    <span style="background:#F3F4F6;padding:3px 8px;border-radius:5px;font-size:0.7rem;color:#555;">USD</span>
                    <span style="background:#F3F4F6;padding:3px 8px;border-radius:5px;font-size:0.7rem;color:#555;">Last 7 Days</span>
                </div>
            </div>
        </div>""", unsafe_allow_html=True)
        savings = run_query(f"SELECT SNAPSHOT_DATE, DOLLAR_SAVED FROM {DB}.{SCHEMA}.SAVINGS_HISTORY ORDER BY SNAPSHOT_DATE")
        if not savings.empty:
            st.line_chart(savings.set_index("SNAPSHOT_DATE"))
        else:
            st.info("No savings history yet. Run detection + apply fixes to populate.")

    with ch2:
        st.markdown("""<div style="background:#fff;border:1px solid #E8ECF0;border-radius:12px;padding:20px;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
                <span style="font-size:0.95rem;font-weight:600;color:#1a1a2e;">Anomalies by Warehouse</span>
                <div style="display:flex;gap:6px;">
                    <span style="background:#F3F4F6;padding:3px 8px;border-radius:5px;font-size:0.7rem;color:#555;">Credits</span>
                    <span style="background:#F3F4F6;padding:3px 8px;border-radius:5px;font-size:0.7rem;color:#555;">All Time</span>
                </div>
            </div>
        </div>""", unsafe_allow_html=True)
        chart_data = run_query(f"""
            SELECT WAREHOUSE_NAME, ANOMALY_TYPE, SUM(CREDITS_WASTED) AS CREDITS
            FROM {DB}.{SCHEMA}.USAGE_ANOMALIES GROUP BY 1, 2 ORDER BY CREDITS DESC
        """)
        if not chart_data.empty:
            pivot = chart_data.pivot_table(index="WAREHOUSE_NAME", columns="ANOMALY_TYPE", values="CREDITS", aggfunc="sum").fillna(0)
            st.bar_chart(pivot)

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

    # Warehouse Health Scores
    st.markdown("""
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
        <span style="font-size:1.1rem;font-weight:600;color:#1a1a2e;">Warehouse Health Scores</span>
        <span style="color:#667eea;font-size:0.82rem;cursor:pointer;">View all warehouses →</span>
    </div>
    """, unsafe_allow_html=True)

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

            score_cols = st.columns(min(len(wh_all), 3))
            for i, (_, row) in enumerate(wh_all.iterrows()):
                wh_name = row["WH"]
                auto_sus = int(row["AUTO_SUSPEND"] or 600)
                anomalies = int(anomaly_map.get(wh_name, 0))

                score = 100
                if auto_sus > 300:
                    score -= 15
                if auto_sus > 600:
                    score -= 10
                if row["STATE"] == "STARTED" and int(row["RUNNING"] or 0) == 0:
                    score -= 20
                score -= min(anomalies * 8, 40)
                score = max(score, 0)

                col_idx = i % min(len(wh_all), 3)
                with score_cols[col_idx]:
                    st.markdown(render_health_card(wh_name, score, row["STATE"]), unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Could not compute health scores: {e}")

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

    # Environmental Impact section
    st.markdown("""<div style="font-size:1.1rem;font-weight:600;color:#1a1a2e;margin-bottom:12px;">🌍 Environmental Impact</div>""", unsafe_allow_html=True)
    eco1, eco2, eco3 = st.columns(3)
    kwh_saved = credits_saved * KWH_PER_CREDIT
    with eco1:
        st.markdown(render_kpi_card("⚡", "rgba(59,130,246,0.1)", "Energy Saved", f"{kwh_saved:.1f} kWh", "", True), unsafe_allow_html=True)
    with eco2:
        st.markdown(render_kpi_card("🌱", "rgba(22,163,74,0.1)", "CO2 Avoided", f"{co2_saved:.1f} kg", "", True), unsafe_allow_html=True)
    with eco3:
        st.markdown(render_kpi_card("🌳", "rgba(22,163,74,0.1)", "Equivalent Trees", f"{max(1, int(co2_saved / 21.77))}", "", True), unsafe_allow_html=True)

    # Footer
    st.markdown("""
    <div style="text-align:center;margin-top:32px;padding:12px;color:#aaa;font-size:0.75rem;">
        ℹ️ All times shown in your local timezone · Based on US avg grid emissions (0.39 kg CO2/kWh)
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# TAB 2: OPERATIONS
# ============================================================
elif "Operations" in tab_choice:
    render_page_header("Operations Center", "⚙️")

    # Warehouse Status
    st.markdown("""<div style="font-size:1.05rem;font-weight:600;color:#1a1a2e;margin-bottom:12px;">🖥️ Warehouse Status (Live)</div>""", unsafe_allow_html=True)
    try:
        session.sql("SHOW WAREHOUSES").collect()
        wh_raw = run_query("""
            SELECT "name" AS WAREHOUSE, "state" AS STATUS, "size" AS SIZE,
                   "auto_suspend" AS AUTO_SUSPEND_SEC, "running" AS RUNNING, "queued" AS QUEUED
            FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
        """)
        if not wh_raw.empty:
            for _, wrow in wh_raw.iterrows():
                state = wrow["STATUS"]
                if state == "STARTED":
                    badge = '<span style="background:rgba(22,163,74,0.1);color:#16A34A;padding:4px 10px;border-radius:6px;font-size:0.75rem;font-weight:500;">● Running</span>'
                elif state == "SUSPENDED":
                    badge = '<span style="background:rgba(107,114,128,0.1);color:#6B7280;padding:4px 10px;border-radius:6px;font-size:0.75rem;font-weight:500;">⏸ Suspended</span>'
                else:
                    badge = f'<span style="background:rgba(245,158,11,0.1);color:#F59E0B;padding:4px 10px;border-radius:6px;font-size:0.75rem;font-weight:500;">{state}</span>'
                st.markdown(f"""
                <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 18px;margin:6px 0;border-radius:10px;background:#fff;border:1px solid #E8ECF0;">
                    <span style="font-weight:600;color:#1a1a2e;">{wrow['WAREHOUSE']}</span>
                    {badge}
                    <span style="color:#666;font-size:0.85rem;">Size: <code style="background:#F3F4F6;padding:2px 6px;border-radius:4px;">{wrow['SIZE']}</code></span>
                    <span style="color:#666;font-size:0.85rem;">Suspend: <code style="background:#F3F4F6;padding:2px 6px;border-radius:4px;">{wrow['AUTO_SUSPEND_SEC']}s</code></span>
                </div>""", unsafe_allow_html=True)
    except Exception:
        pass

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # Auto-applied fixes
    st.markdown("""<div style="font-size:1.05rem;font-weight:600;color:#1a1a2e;margin-bottom:12px;">🤖 Recently Auto-Applied Fixes</div>""", unsafe_allow_html=True)
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

    # Footer
    # --- Smart Alerts: Natural Language ---
    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    st.markdown("""<div style="font-size:1.05rem;font-weight:600;color:#1a1a2e;margin-bottom:4px;">🔔 Smart Alerts — Natural Language</div>""", unsafe_allow_html=True)
    st.markdown("""<p style="color:#888;font-size:0.82rem;margin-bottom:12px;">Create monitoring rules in plain English. AI parses them into structured alerts.</p>""", unsafe_allow_html=True)

    alert_input = st.text_input("Describe your alert rule...", placeholder="e.g. Notify me if any warehouse spends more than $50 per day", key="alert_nl")

    if alert_input:
        try:
            import json as _json
            parse_prompt = (
                "Parse this monitoring alert rule into JSON. Return ONLY valid JSON, no explanation.\\n"
                "Format: {\"metric\": \"...\", \"threshold\": ..., \"warehouse\": \"...\", \"condition\": \"...\"}\\n"
                "Valid metrics: daily_spend, weekly_spend, credits_per_hour, idle_minutes, query_count\\n"
                "Valid conditions: greater_than, less_than, equals\\n"
                "If no warehouse specified, use ANY.\\n\\n"
                f"Rule: {alert_input}"
            )
            safe_parse = parse_prompt.replace("'", "\\'")
            parse_result = run_query(f"SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large2', '{safe_parse}') AS RESPONSE")
            raw_response = parse_result["RESPONSE"].iloc[0]

            # Extract JSON from response
            json_start = raw_response.find("{")
            json_end = raw_response.rfind("}") + 1
            parsed = _json.loads(raw_response[json_start:json_end])

            metric = parsed.get("metric", "daily_spend")
            threshold = float(parsed.get("threshold", 0))
            warehouse = parsed.get("warehouse", "ANY")
            condition = parsed.get("condition", "greater_than")

            cond_symbol = ">" if condition == "greater_than" else "<" if condition == "less_than" else "="
            metric_icon = "💰" if "spend" in metric else "⏱" if "idle" in metric or "hour" in metric else "📊"

            st.markdown(f"""
            <div style="background:#fff;border:1px solid #E8ECF0;border-radius:12px;padding:16px 20px;margin-top:12px;">
                <div style="font-size:0.75rem;color:#667eea;font-weight:500;margin-bottom:10px;">🤖 Parsed Alert Rule</div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
                    <span style="background:rgba(102,126,234,0.08);color:#4338CA;padding:4px 12px;border-radius:6px;font-size:0.8rem;font-weight:500;">{metric_icon} {metric}</span>
                    <span style="background:rgba(220,38,38,0.08);color:#DC2626;padding:4px 12px;border-radius:6px;font-size:0.8rem;font-weight:500;">{cond_symbol} {threshold}</span>
                    <span style="background:rgba(22,163,74,0.08);color:#16A34A;padding:4px 12px;border-radius:6px;font-size:0.8rem;font-weight:500;">🖥 {warehouse}</span>
                </div>
                <div style="font-size:0.82rem;color:#555;">"{alert_input}"</div>
            </div>
            """, unsafe_allow_html=True)

            if st.button("✅ Activate Alert", type="primary", key="activate_alert"):
                safe_rule = alert_input.replace("'", "''")
                safe_wh = warehouse.replace("'", "''")
                session.sql(f"""
                    INSERT INTO {DB}.{SCHEMA}.SMART_ALERTS (NATURAL_LANGUAGE_RULE, PARSED_METRIC, PARSED_THRESHOLD, PARSED_WAREHOUSE, PARSED_CONDITION)
                    VALUES ('{safe_rule}', '{metric}', {threshold}, '{safe_wh}', '{condition}')
                """).collect()
                st.success("Alert activated!")
                st.experimental_rerun()
        except Exception as e:
            st.error(f"Could not parse alert: {e}")

    # Show active alerts
    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
    active_alerts = run_query(f"SELECT * FROM {DB}.{SCHEMA}.SMART_ALERTS WHERE IS_ACTIVE = TRUE ORDER BY CREATED_AT DESC")
    if not active_alerts.empty:
        st.markdown(f"""<div style="font-size:0.9rem;font-weight:600;color:#1a1a2e;margin-bottom:10px;">Active Alerts ({len(active_alerts)})</div>""", unsafe_allow_html=True)
        for _, alert in active_alerts.iterrows():
            a_metric = alert["PARSED_METRIC"]
            a_thresh = alert["PARSED_THRESHOLD"]
            a_wh = alert["PARSED_WAREHOUSE"]
            a_cond = alert["PARSED_CONDITION"]
            a_rule = alert["NATURAL_LANGUAGE_RULE"]
            a_id = int(alert["ALERT_ID"])
            triggered = alert["TRIGGER_COUNT"]

            cond_sym = ">" if a_cond == "greater_than" else "<" if a_cond == "less_than" else "="
            status_badge = f'<span style="background:rgba(22,163,74,0.1);color:#16A34A;padding:3px 10px;border-radius:6px;font-size:0.72rem;font-weight:500;">🟢 Active</span>' if triggered == 0 else f'<span style="background:rgba(220,38,38,0.1);color:#DC2626;padding:3px 10px;border-radius:6px;font-size:0.72rem;font-weight:500;">🔴 Triggered ({triggered}x)</span>'

            st.markdown(f"""
            <div style="background:#fff;border:1px solid #E8ECF0;border-radius:10px;padding:14px 18px;margin-bottom:8px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <span style="font-size:0.82rem;font-weight:500;color:#1a1a2e;">{a_rule}</span>
                    {status_badge}
                </div>
                <div style="display:flex;gap:6px;">
                    <span style="background:#F3F4F6;padding:3px 8px;border-radius:4px;font-size:0.72rem;color:#555;">{a_metric} {cond_sym} {a_thresh}</span>
                    <span style="background:#F3F4F6;padding:3px 8px;border-radius:4px;font-size:0.72rem;color:#555;">🖥 {a_wh}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button(f"🗑 Delete", key=f"del_alert_{a_id}"):
                session.sql(f"UPDATE {DB}.{SCHEMA}.SMART_ALERTS SET IS_ACTIVE = FALSE WHERE ALERT_ID = {a_id}").collect()
                st.experimental_rerun()
    else:
        st.markdown("""<div style="background:#F9FAFB;border:1px dashed #D1D5DB;border-radius:10px;padding:20px;text-align:center;color:#888;font-size:0.85rem;">No active alerts yet. Create one above using natural language!</div>""", unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center;margin-top:32px;padding:12px;color:#aaa;font-size:0.75rem;">
        ℹ️ All times shown in your local timezone
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# TAB: APPROVALS
# ============================================================
elif "Approvals" in tab_choice:
    render_page_header("Approvals", "✅")

    # Pending approvals count
    pending = run_query(f"""
        SELECT a.ANOMALY_ID, a.WAREHOUSE_NAME, a.ANOMALY_TYPE, a.SEVERITY,
               a.CREDITS_WASTED, a.DESCRIPTION, l.SQL_EXECUTED AS PROPOSED_FIX
        FROM {DB}.{SCHEMA}.USAGE_ANOMALIES a
        JOIN {DB}.{SCHEMA}.AUDIT_LOG l ON l.ANOMALY_ID = a.ANOMALY_ID
        WHERE a.STATUS = 'ACKNOWLEDGED' AND l.STATUS = 'PENDING_APPROVAL'
        ORDER BY a.CREDITS_WASTED DESC
    """)

    # KPI summary
    total_pending = len(pending)
    total_risk = pending["CREDITS_WASTED"].sum() * CREDIT_RATE if not pending.empty else 0
    high_count = len(pending[pending["SEVERITY"].isin(["HIGH", "CRITICAL"])]) if not pending.empty else 0

    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown(render_kpi_card("⏳", "rgba(245,158,11,0.1)", "Pending Approvals", str(total_pending), "", total_pending == 0), unsafe_allow_html=True)
    with k2:
        st.markdown(render_kpi_card("💰", "rgba(220,38,38,0.1)", "Total $ at Risk", f"${total_risk:.2f}", "", False), unsafe_allow_html=True)
    with k3:
        st.markdown(render_kpi_card("🚨", "rgba(220,38,38,0.1)", "High Severity", str(high_count), "", high_count == 0), unsafe_allow_html=True)

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    if not pending.empty:
        st.markdown("""<div style="font-size:1.05rem;font-weight:600;color:#1a1a2e;margin-bottom:12px;">🔐 Pending Approvals</div>""", unsafe_allow_html=True)
        for _, row in pending.iterrows():
            severity = row['SEVERITY']
            sev_color = "#DC2626" if severity in ("HIGH", "CRITICAL") else "#F59E0B" if severity == "MEDIUM" else "#3B82F6"
            dollar_risk = float(row["CREDITS_WASTED"]) * CREDIT_RATE
            st.markdown(f"""
            <div style="border:1px solid #E8ECF0;border-left:4px solid {sev_color};border-radius:0 10px 10px 0;padding:14px 18px;margin:10px 0;background:#fff;">
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
                    <span style="font-weight:600;font-size:1rem;color:#1a1a2e;">{row['WAREHOUSE_NAME']}</span>
                    <span style="background:{sev_color};color:white;padding:2px 8px;border-radius:5px;font-size:0.72rem;font-weight:500;">{severity}</span>
                    <span style="color:#666;font-size:0.85rem;">{row['ANOMALY_TYPE']}</span>
                </div>
                <div style="color:#555;font-size:0.88rem;margin-bottom:6px;">{row['DESCRIPTION']}</div>
                <div style="font-weight:600;color:{sev_color};font-size:0.9rem;">${dollar_risk:.2f} at risk <span style="color:#888;font-weight:400;">({float(row['CREDITS_WASTED']):.2f} credits)</span></div>
            </div>""", unsafe_allow_html=True)
            p1, p2, p3 = st.columns([4, 1, 1])
            with p1:
                st.code(row["PROPOSED_FIX"], language="sql")
            with p2:
                aid = int(row["ANOMALY_ID"])
                if st.button("✓ Approve", key=f"ap_{aid}", type="primary", use_container_width=True):
                    session.sql(f"CALL {DB}.{SCHEMA}.APPROVE_FIX({aid}, CURRENT_USER())").collect()
                    st.success("Approved!")
                    st.experimental_rerun()
            with p3:
                if st.button("✗ Dismiss", key=f"dm_{aid}", use_container_width=True):
                    session.sql(f"UPDATE {DB}.{SCHEMA}.USAGE_ANOMALIES SET STATUS='DISMISSED' WHERE ANOMALY_ID={aid}").collect()
                    session.sql(f"UPDATE {DB}.{SCHEMA}.AUDIT_LOG SET STATUS='COMPLETED',APPROVED_BY=CURRENT_USER() WHERE ANOMALY_ID={aid} AND STATUS='PENDING_APPROVAL'").collect()
                    st.experimental_rerun()
    else:
        st.markdown("""<div style="background:rgba(22,163,74,0.06);border:1px solid rgba(22,163,74,0.2);border-radius:10px;padding:14px 18px;color:#16A34A;font-size:0.9rem;">✅ No pending approvals — all clear!</div>""", unsafe_allow_html=True)

    # Recently approved
    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    st.markdown("""<div style="font-size:1.05rem;font-weight:600;color:#1a1a2e;margin-bottom:12px;">✔️ Recently Approved</div>""", unsafe_allow_html=True)
    recent_approved = run_query(f"""
        SELECT l.LOGGED_AT, l.WAREHOUSE_NAME, a.ANOMALY_TYPE, a.SEVERITY,
               ROUND(a.CREDITS_WASTED * {CREDIT_RATE}, 2) AS DOLLAR_SAVED, l.APPROVED_BY
        FROM {DB}.{SCHEMA}.AUDIT_LOG l
        JOIN {DB}.{SCHEMA}.USAGE_ANOMALIES a ON a.ANOMALY_ID = l.ANOMALY_ID
        WHERE l.ACTION_TYPE = 'USER_ACTION' AND l.STATUS = 'COMPLETED' AND l.APPROVED_BY IS NOT NULL
        ORDER BY l.LOGGED_AT DESC LIMIT 5
    """)
    if not recent_approved.empty:
        for _, ra in recent_approved.iterrows():
            st.markdown(f"""
            <div style="display:flex;align-items:center;padding:12px 18px;border-bottom:1px solid #F3F4F6;">
                <div style="width:36px;height:36px;min-width:36px;background:rgba(22,163,74,0.1);border-radius:50%;display:flex;align-items:center;justify-content:center;margin-right:12px;">
                    <span style="color:#16A34A;font-size:1rem;">✅</span>
                </div>
                <div style="flex:1;">
                    <div style="font-weight:600;color:#1a1a2e;font-size:0.9rem;">{ra['WAREHOUSE_NAME']} — {ra['ANOMALY_TYPE']}</div>
                    <div style="color:#888;font-size:0.78rem;">{ra['LOGGED_AT']} · Approved by {ra['APPROVED_BY']}</div>
                </div>
                <span style="color:#16A34A;font-weight:600;font-size:0.88rem;">${ra['DOLLAR_SAVED']} saved</span>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No recently approved actions.")

    st.markdown("""
    <div style="text-align:center;margin-top:32px;padding:12px;color:#aaa;font-size:0.75rem;">
        ℹ️ All times shown in your local timezone
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# TAB 3: INTELLIGENCE
# ============================================================
elif "Intelligence" in tab_choice:
    render_page_header("AI Intelligence", "🧠")

    # AI Chat
    st.markdown("""<div style="font-size:1.05rem;font-weight:600;color:#1a1a2e;margin-bottom:12px;">💬 Ask FinOps Guardian</div>""", unsafe_allow_html=True)
    user_q = st.text_input("Ask a question about your Snowflake costs...")
    if user_q:
        try:
            context_df = run_query(f"""
                SELECT WAREHOUSE_NAME, ANOMALY_TYPE, SEVERITY, CREDITS_WASTED, STATUS
                FROM {DB}.{SCHEMA}.USAGE_ANOMALIES ORDER BY DETECTED_AT DESC LIMIT 15
            """)
            prompt = (
                "You are FinOps Guardian, an AI assistant for Snowflake cost optimization. "
                "Answer concisely with specific numbers and actionable recommendations.\\n\\n"
                f"Current anomaly data:\\n{context_df.to_string(index=False)}\\n\\n"
                f"Credit rate: ${CREDIT_RATE}/credit. "
                f"Total credits saved so far: {context_df[context_df['STATUS']=='RESOLVED']['CREDITS_WASTED'].sum():.2f}\\n\\n"
                f"Question: {user_q}"
            )
            safe_prompt = prompt.replace("'", "\\'")
            answer_df = run_query(f"SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large2', '{safe_prompt}') AS RESPONSE")
            answer = answer_df["RESPONSE"].iloc[0]
            st.markdown(f"""<div style="background:#fff;border:1px solid #E8ECF0;border-radius:12px;padding:16px 20px;margin-top:12px;">
                <div style="font-size:0.75rem;color:#667eea;font-weight:500;margin-bottom:8px;">🤖 AI Response</div>
                <div style="color:#333;font-size:0.9rem;line-height:1.6;">{answer}</div>
            </div>""", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"AI error: {e}")

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # Cost Attribution
    st.markdown("""<div style="font-size:1.05rem;font-weight:600;color:#1a1a2e;margin-bottom:12px;">👥 Cost Attribution (Top Users - 7 Days)</div>""", unsafe_allow_html=True)
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

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # Week-over-Week
    st.markdown("""<div style="font-size:1.05rem;font-weight:600;color:#1a1a2e;margin-bottom:12px;">📈 Week-over-Week Comparison</div>""", unsafe_allow_html=True)
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

    st.markdown("""
    <div style="text-align:center;margin-top:32px;padding:12px;color:#aaa;font-size:0.75rem;">
        ℹ️ All times shown in your local timezone
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# TAB 4: COMPLIANCE
# ============================================================
elif "Compliance" in tab_choice:
    render_page_header("Policy Compliance", "📋")

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

                total_checks += 1
                if auto_sus <= 300:
                    passed_checks += 1
                else:
                    severity = "HIGH" if auto_sus > 600 else "MEDIUM"
                    findings.append({
                        "Warehouse": name, "Check": "Auto-Suspend Timeout",
                        "Status": "FAIL", "Severity": severity,
                        "Current": f"{auto_sus}s", "Recommended": "60-300s",
                        "Fix": f"ALTER WAREHOUSE {name} SET AUTO_SUSPEND = 60;"
                    })

                total_checks += 1
                if str(wh["AUTO_RESUME"]).lower() == "true":
                    passed_checks += 1
                else:
                    findings.append({
                        "Warehouse": name, "Check": "Auto-Resume Disabled",
                        "Status": "FAIL", "Severity": "LOW",
                        "Current": "false", "Recommended": "true",
                        "Fix": f"ALTER WAREHOUSE {name} SET AUTO_RESUME = TRUE;"
                    })

                total_checks += 1
                large_sizes = ["Large", "X-Large", "2X-Large", "3X-Large", "4X-Large"]
                if size in large_sizes and "ETL" not in name.upper():
                    findings.append({
                        "Warehouse": name, "Check": "Potentially Oversized",
                        "Status": "WARN", "Severity": "MEDIUM",
                        "Current": size, "Recommended": "Review utilization",
                        "Fix": f"-- Review WAREHOUSE_LOAD_HISTORY for {name}"
                    })
                else:
                    passed_checks += 1

            compliance_pct = int((passed_checks / total_checks) * 100) if total_checks > 0 else 100

            # Compliance KPIs
            sc1, sc2, sc3 = st.columns(3)
            score_color = "rgba(22,163,74,0.1)" if compliance_pct >= 80 else "rgba(245,158,11,0.1)" if compliance_pct >= 50 else "rgba(220,38,38,0.1)"
            score_icon = "✅" if compliance_pct >= 80 else "⚠️" if compliance_pct >= 50 else "❌"
            with sc1:
                st.markdown(render_kpi_card(score_icon, score_color, "Compliance Score", f"{compliance_pct}%", "", compliance_pct >= 80), unsafe_allow_html=True)
            with sc2:
                st.markdown(render_kpi_card("✔️", "rgba(22,163,74,0.1)", "Checks Passed", f"{passed_checks}/{total_checks}", "", True), unsafe_allow_html=True)
            with sc3:
                st.markdown(render_kpi_card("🔍", "rgba(59,130,246,0.1)", "Issues Found", str(len(findings)), "", len(findings) == 0), unsafe_allow_html=True)

            st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

            if findings:
                st.markdown("""<div style="font-size:1.05rem;font-weight:600;color:#1a1a2e;margin-bottom:12px;">Policy Violations</div>""", unsafe_allow_html=True)
                for f in findings:
                    sev_color = "#DC2626" if f['Severity'] == "HIGH" else "#F59E0B" if f['Severity'] == "MEDIUM" else "#3B82F6"
                    with st.expander(f"{f['Severity']} | {f['Warehouse']} - {f['Check']}"):
                        fc1, fc2 = st.columns(2)
                        with fc1:
                            st.markdown(f"**Current value:** `{f['Current']}`")
                            st.markdown(f"**Recommended:** `{f['Recommended']}`")
                        with fc2:
                            st.code(f["Fix"], language="sql")
            else:
                st.markdown("""<div style="background:rgba(22,163,74,0.06);border:1px solid rgba(22,163,74,0.2);border-radius:10px;padding:14px 18px;color:#16A34A;font-size:0.9rem;">✅ All warehouses comply with best practices!</div>""", unsafe_allow_html=True)

            st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
            st.markdown("""<div style="font-size:1.05rem;font-weight:600;color:#1a1a2e;margin-bottom:12px;">Best Practice Reference</div>""", unsafe_allow_html=True)
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

    st.markdown("""
    <div style="text-align:center;margin-top:32px;padding:12px;color:#aaa;font-size:0.75rem;">
        ℹ️ All times shown in your local timezone
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# TAB 5: NOTIFICATIONS
# ============================================================
elif "Notifications" in tab_choice:
    render_page_header("Notifications", "🔔")

    notifs = run_query(f"""
        SELECT NOTIFICATION_ID, CREATED_AT, NOTIFICATION_TYPE, TITLE, MESSAGE,
               WAREHOUSE_NAME, IS_READ
        FROM {DB}.{SCHEMA}.NOTIFICATIONS
        ORDER BY CREATED_AT DESC
        LIMIT 30
    """)

    unread_notifs = notifs[notifs["IS_READ"] == False] if not notifs.empty else notifs
    read_notifs = notifs[notifs["IS_READ"] == True] if not notifs.empty else notifs
    total_unread = len(unread_notifs)

    # Header row: count + mark all read
    n1, n2 = st.columns([3, 1])
    with n1:
        st.markdown(f"<span style='font-size:0.9rem;color:#555;'><strong>{total_unread}</strong> unread notifications</span>", unsafe_allow_html=True)
    with n2:
        if st.button("✓ Mark all read", use_container_width=True):
            session.sql(f"UPDATE {DB}.{SCHEMA}.NOTIFICATIONS SET IS_READ = TRUE WHERE IS_READ = FALSE").collect()
            st.experimental_rerun()

    # Filter tabs
    alert_count = len(notifs[notifs["NOTIFICATION_TYPE"] == "APPROVAL_NEEDED"]) if not notifs.empty else 0
    info_count = len(notifs[notifs["NOTIFICATION_TYPE"] == "INFO"]) if not notifs.empty else 0
    success_count = len(notifs[notifs["NOTIFICATION_TYPE"] == "APPROVED"]) if not notifs.empty else 0
    warning_count = len(notifs[notifs["NOTIFICATION_TYPE"] == "WARNING"]) if not notifs.empty else 0

    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:20px;padding:12px 0;border-bottom:2px solid #E8ECF0;margin:12px 0 16px 0;">
        <span style="font-size:0.85rem;font-weight:600;color:#667eea;border-bottom:2px solid #667eea;padding-bottom:10px;margin-bottom:-14px;">All</span>
        <span style="font-size:0.85rem;color:#555;">Unread <span style="background:#E8ECF0;padding:1px 6px;border-radius:4px;font-size:0.75rem;">{total_unread}</span></span>
        <span style="font-size:0.85rem;color:#555;"><span style="color:#DC2626;">●</span> Alerts</span>
        <span style="font-size:0.85rem;color:#555;"><span style="color:#F59E0B;">●</span> Warnings</span>
        <span style="font-size:0.85rem;color:#555;"><span style="color:#3B82F6;">●</span> Info</span>
        <span style="font-size:0.85rem;color:#555;"><span style="color:#16A34A;">●</span> Success</span>
    </div>
    """, unsafe_allow_html=True)

    if notifs.empty:
        st.info("No notifications yet. Run detection scans and apply fixes to generate notifications.")
    else:
        # Render notification cards matching reference design
        from datetime import datetime as dt
        now = dt.now()

        for _, n in notifs.iterrows():
            ntype = n["NOTIFICATION_TYPE"]
            # Determine icon and badge based on type
            if ntype == "APPROVAL_NEEDED":
                icon_bg = "rgba(220,38,38,0.1)"
                icon_svg = '<span style="color:#DC2626;font-size:1.2rem;">⚠️</span>'
                badge_color = "#DC2626"
                badge_bg = "rgba(220,38,38,0.08)"
                badge_label = "High"
            elif ntype == "APPROVED":
                icon_bg = "rgba(22,163,74,0.1)"
                icon_svg = '<span style="color:#16A34A;font-size:1.2rem;">✅</span>'
                badge_color = "#16A34A"
                badge_bg = "rgba(22,163,74,0.08)"
                badge_label = "Success"
            elif ntype == "WARNING":
                icon_bg = "rgba(245,158,11,0.1)"
                icon_svg = '<span style="color:#F59E0B;font-size:1.2rem;">⚠️</span>'
                badge_color = "#F59E0B"
                badge_bg = "rgba(245,158,11,0.08)"
                badge_label = "Warning"
            else:
                icon_bg = "rgba(59,130,246,0.1)"
                icon_svg = '<span style="color:#3B82F6;font-size:1.2rem;">ℹ️</span>'
                badge_color = "#3B82F6"
                badge_bg = "rgba(59,130,246,0.08)"
                badge_label = "Info"

            # Time ago
            try:
                created = n["CREATED_AT"]
                if hasattr(created, 'to_pydatetime'):
                    created = created.to_pydatetime()
                diff = now - created.replace(tzinfo=None)
                minutes = int(diff.total_seconds() / 60)
                if minutes < 60:
                    time_ago = f"{minutes}m ago"
                elif minutes < 1440:
                    time_ago = f"{minutes // 60}h ago"
                else:
                    time_ago = f"{minutes // 1440}d ago"
            except Exception:
                time_ago = str(n["CREATED_AT"])

            st.markdown(f"""
            <div style="display:flex;align-items:center;padding:16px 20px;border-bottom:1px solid #F3F4F6;">
                <div style="width:40px;height:40px;min-width:40px;background:{icon_bg};border-radius:50%;display:flex;align-items:center;justify-content:center;margin-right:14px;">
                    {icon_svg}
                </div>
                <div style="flex:1;">
                    <div style="font-weight:600;color:#1a1a2e;font-size:0.92rem;margin-bottom:3px;">{n['TITLE']}</div>
                    <div style="color:#666;font-size:0.83rem;margin-bottom:4px;">{n['MESSAGE']}</div>
                    <div style="color:#999;font-size:0.75rem;">{time_ago} · {n['WAREHOUSE_NAME']}</div>
                </div>
                <div style="margin-left:16px;display:flex;align-items:center;gap:10px;">
                    <span style="background:{badge_bg};color:{badge_color};padding:4px 12px;border-radius:6px;font-size:0.78rem;font-weight:500;">{badge_label}</span>
                    <span style="color:#ccc;font-size:1rem;">›</span>
                </div>
            </div>""", unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center;margin-top:32px;padding:12px;color:#aaa;font-size:0.75rem;">
        ℹ️ All times shown in your local timezone
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# TAB 6: AUDIT TRAIL
# ============================================================
elif "Audit Trail" in tab_choice:
    render_page_header("Audit Trail", "📜")

    # Summary KPIs
    audit_stats = run_query(f"""
        SELECT
            COUNT(*) AS TOTAL_ENTRIES,
            COUNT(CASE WHEN ACTION_TYPE = 'AUTO_ACTION' THEN 1 END) AS AUTO_ACTIONS,
            COUNT(CASE WHEN ACTION_TYPE = 'USER_ACTION' THEN 1 END) AS MANUAL_ACTIONS,
            COUNT(CASE WHEN STATUS = 'PENDING_APPROVAL' THEN 1 END) AS PENDING
        FROM {DB}.{SCHEMA}.AUDIT_LOG
    """)
    as1, as2, as3, as4 = st.columns(4)
    with as1:
        st.markdown(render_kpi_card("📋", "rgba(59,130,246,0.1)", "Total Entries", str(int(audit_stats["TOTAL_ENTRIES"].iloc[0])), "", True), unsafe_allow_html=True)
    with as2:
        st.markdown(render_kpi_card("🤖", "rgba(118,75,162,0.1)", "Auto Actions", str(int(audit_stats["AUTO_ACTIONS"].iloc[0])), "", True), unsafe_allow_html=True)
    with as3:
        st.markdown(render_kpi_card("👤", "rgba(22,163,74,0.1)", "Manual Actions", str(int(audit_stats["MANUAL_ACTIONS"].iloc[0])), "", True), unsafe_allow_html=True)
    with as4:
        st.markdown(render_kpi_card("⏳", "rgba(245,158,11,0.1)", "Pending", str(int(audit_stats["PENDING"].iloc[0])), "", int(audit_stats["PENDING"].iloc[0]) == 0), unsafe_allow_html=True)

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

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

    st.markdown("""
    <div style="text-align:center;margin-top:32px;padding:12px;color:#aaa;font-size:0.75rem;">
        ℹ️ All times shown in your local timezone
    </div>
    """, unsafe_allow_html=True)
