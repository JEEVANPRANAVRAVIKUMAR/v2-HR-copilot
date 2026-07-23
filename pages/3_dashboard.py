"""
Dashboard page — workforce analytics with KPIs, charts, and AI summary.
"""

from __future__ import annotations

import streamlit as st

from ui_helpers import (
    load_css,
    render_sidebar,
    metric_card,
    bar_chart,
    donut_chart,
    loading_placeholder,
    empty_state,
    show_error,
)

st.set_page_config(
    page_title="📊 Dashboard",
    page_icon="📊",
    layout="wide",
)

load_css()
render_sidebar()

st.markdown(
    '<h2 style="color:#1A365D;margin:0 0 0.5rem;">📊 Workforce Dashboard</h2>',
    unsafe_allow_html=True,
)

# ---- Lazy init AnalyticsAgent ----
if "analytics_agent" not in st.session_state:
    try:
        from config import get_settings
        from database.client import DatabaseClient
        from database.queries import AnalyticsRepository
        from ai import GroqLLM, AnalyticsAgent
        from utils.logger import get_logger

        settings = get_settings()
        logger = get_logger("dashboard_page")
        DatabaseClient.get_client()  # ensure singleton initialized
        llm = GroqLLM(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            logger=logger,
        )
        repo = AnalyticsRepository()
        st.session_state.analytics_agent = AnalyticsAgent(repo, llm, logger)
    except Exception as exc:
        st.session_state.analytics_agent = None
        st.error(f"Failed to initialize analytics: {exc}")


placeholder = loading_placeholder("dashboard")

with placeholder.container():
    if st.session_state.analytics_agent is None:
        empty_state(
            "📊",
            "Analytics unavailable",
            "Check your database configuration and try again.",
        )
    else:
        with st.spinner("Loading dashboard data..."):
            try:
                agent = st.session_state.analytics_agent
                data = agent.full_snapshot()
                ai_summary = agent.explain_snapshot()
            except Exception as exc:
                show_error(str(exc))
                data = {}
                ai_summary = ""

        # ---- KPI row ----
        kp1, kp2, kp3, kp4 = st.columns(4)
        with kp1:
            metric_card(
                "Total Employees",
                data.get("total_headcount", 0),
            )
        with kp2:
            metric_card(
                "Avg Tenure",
                f"{data.get('average_tenure_years', 0):.1f} yrs",
            )
        with kp3:
            dept_count = len(data.get("by_department", []))
            metric_card("Departments", dept_count)
        with kp4:
            active_count = sum(
                d.get("count", 0)
                for d in data.get("by_status", [])
                if d.get("status", "").lower() in ("active", "permanent")
            )
            total = data.get("total_headcount", 1)
            metric_card(
                "Active Rate",
                f"{active_count / total * 100:.0f}%" if total else "0%",
            )

        # ---- Charts ----
        c1, c2 = st.columns(2)

        with c1:
            dept_data = data.get("by_department", [])
            if dept_data:
                import pandas as pd
                df_dept = pd.DataFrame(dept_data)
                fig = bar_chart(df_dept, x="department", y="count", title="Employees by Department")
                st.plotly_chart(fig, use_container_width=True)

            status_data = data.get("by_status", [])
            if status_data:
                labels = [d.get("status", "Unknown") for d in status_data]
                values = [d.get("count", 0) for d in status_data]
                fig = donut_chart(labels, values, title="By Status")
                st.plotly_chart(fig, use_container_width=True)

        with c2:
            gender_data = data.get("by_gender", [])
            if gender_data:
                labels = [d.get("gender", "Unknown") for d in gender_data]
                values = [d.get("count", 0) for d in gender_data]
                fig = donut_chart(labels, values, title="Gender Breakdown")
                st.plotly_chart(fig, use_container_width=True)

            hiring_year = data.get("hiring_by_year", [])
            if hiring_year:
                import pandas as pd
                df_hy = pd.DataFrame(hiring_year)
                fig = bar_chart(df_hy, x="year", y="hires", title="Hiring by Year")
                st.plotly_chart(fig, use_container_width=True)

        # ---- AI Summary ----
        if ai_summary:
            st.markdown(
                f'<div class="card">'
                f"<h3>🤖 AI Summary</h3>"
                f"<p style='color:#0F172A;'>{ai_summary}</p>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # ---- Tenure distribution ----
        tenure_data = data.get("tenure_distribution", [])
        if tenure_data:
            import pandas as pd
            df_tenure = pd.DataFrame(tenure_data)
            st.markdown("<h3>Tenure Distribution</h3>", unsafe_allow_html=True)
            st.dataframe(df_tenure, use_container_width=True, hide_index=True)
