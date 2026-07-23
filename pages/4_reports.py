"""
Reports page — generate and download workforce reports in PDF, Excel, or PowerPoint.
"""

from __future__ import annotations

import streamlit as st

from ui_helpers import (
    load_css,
    render_sidebar,
    empty_state,
    show_error,
)

st.set_page_config(
    page_title="📄 Reports",
    page_icon="📄",
    layout="wide",
)

load_css()
render_sidebar()

st.markdown(
    '<h2 style="color:#1A365D;margin:0 0 0.5rem;">📄 Report Generation</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="color:#64748B;margin:0 0 1rem;">'
    "Export workforce analytics as PDF, Excel, or PowerPoint presentations.</p>",
    unsafe_allow_html=True,
)

# ---- Lazy init services ----
if "report_service" not in st.session_state:
    try:
        from config import get_settings
        from database.client import DatabaseClient
        from database.queries import AnalyticsRepository
        from ai import GroqLLM, AnalyticsAgent
        from services.report_service import ReportService
        from utils.logger import get_logger

        settings = get_settings()
        logger = get_logger("reports_page")
        DatabaseClient.get_client()  # ensure singleton initialized

        llm = GroqLLM(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            logger=logger,
        )
        analytics_repo = AnalyticsRepository()
        analytics_agent = AnalyticsAgent(analytics_repo, llm, logger)

        st.session_state.report_service = ReportService(logger)
        st.session_state.analytics_agent = analytics_agent
    except Exception as exc:
        st.session_state.report_service = None
        st.error(f"Failed to initialize report services: {exc}")


if st.session_state.report_service is None:
    empty_state(
        "📄",
        "Report services unavailable",
        "Check your database and API configuration.",
    )
    st.stop()

# ---- Data loading ----
with st.spinner("Loading workforce data..."):
    try:
        data = st.session_state.analytics_agent.full_snapshot()
        ai_summary = st.session_state.analytics_agent.explain_snapshot()
    except Exception as exc:
        show_error(str(exc))
        data = {}
        ai_summary = ""

# ---- KPIs preview ----
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Total Employees", data.get("total_headcount", "N/A"))
with c2:
    st.metric("Average Tenure", f"{data.get('average_tenure_years', 0):.1f} yrs")
with c3:
    st.metric("Departments", len(data.get("by_department", [])))

# ---- Report options ----
st.markdown(
    '<div class="card">'
    "<h3>Export Options</h3>",
    unsafe_allow_html=True,
)

format_col, btn_col = st.columns([1, 1])

with format_col:
    report_format = st.radio(
        "Select format",
        options=["PDF", "Excel", "PowerPoint"],
        horizontal=True,
        help="PDF: formatted report, Excel: multi-sheet workbook, PPT: presentation deck",
    )

with btn_col:
    include_summary = st.checkbox("Include AI summary", value=True)
    st.markdown("<br>", unsafe_allow_html=True)
    generate_clicked = st.button(
        f"Generate {report_format}", type="primary", use_container_width=True,
    )

if generate_clicked:
    with st.spinner(f"Generating {report_format}..."):
        try:
            summary_text = ai_summary if include_summary else ""
            mime_map = {
                "PDF": ("application/pdf", "report.pdf"),
                "Excel": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "report.xlsx",
                ),
                "PowerPoint": (
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "report.pptx",
                ),
            }

            service = st.session_state.report_service
            report_map = {
                "PDF": service.to_pdf,
                "Excel": service.to_excel,
                "PowerPoint": service.to_pptx,
            }

            report_bytes = report_map[report_format](data, summary_text)
            mime_type, filename = mime_map[report_format]

            st.download_button(
                label=f"⬇️ Download {filename}",
                data=report_bytes,
                file_name=filename,
                mime=mime_type,
                use_container_width=True,
            )
            st.success(f"✅ {report_format} report generated successfully!")

        except Exception as exc:
            show_error(str(exc))

st.markdown("</div>", unsafe_allow_html=True)

# ---- AI Summary preview ----
if ai_summary:
    with st.expander("🤖 AI Summary Preview", expanded=False):
        st.markdown(ai_summary)
