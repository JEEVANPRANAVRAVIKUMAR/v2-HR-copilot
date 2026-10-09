"""
Enterprise HR AI Assistant v2.0 — Main entry point.

This is the welcome / home page. CSS is injected here and on every
child page via ``ui_helpers.load_css()``.
"""

import streamlit as st
import os

# Clean up duplicate diagnostics page to avoid Streamlit URL collision
try:
    if os.path.exists("pages/6_diagnostics.py"):
        os.remove("pages/6_diagnostics.py")
except Exception:
    pass

from ui_helpers import load_css, render_sidebar

st.set_page_config(
    page_title="HR AI Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

load_css()
render_sidebar()

st.markdown(
    '<div style="padding:1.5rem 0 1rem;text-align:center;">'
    "<h1 style='color:#1A365D;font-size:2.2rem;margin-bottom:0.4rem;'>"
    "🤖 Enterprise HR AI Assistant</h1>"
    "<p style='color:#64748B;font-size:1.05rem;max-width:650px;margin:0 auto;'>"
    "Manage employees, query workforce intelligence, view interactive analytics, "
    "and generate reports — all powered by specialized AI agents."
    "</p>"
    "</div>",
    unsafe_allow_html=True,
)

st.markdown(
    '<h3 style="color:#1A365D;margin:1rem 0 0.75rem;">🚀 Quick Navigation Hub</h3>',
    unsafe_allow_html=True,
)

def nav_tile(col, icon: str, title: str, description: str, page_path: str, btn_label: str, key_id: str):
    with col:
        with st.container(border=True):
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:0.5rem;margin-bottom:0.25rem;'>"
                f"<span style='font-size:1.4rem;'>{icon}</span>"
                f"<span style='font-weight:700;font-size:1.15rem;color:#1A365D;'>{title}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<p style='color:#64748B;font-size:0.85rem;min-height:42px;margin:0 0 0.75rem;'>{description}</p>",
                unsafe_allow_html=True,
            )
            if st.button(f"{icon} {btn_label}", key=key_id, use_container_width=True, type="primary"):
                st.switch_page(page_path)

row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
nav_tile(row1_col1, "💬", "AI Assistant", "Chat with AI to search employees, look up records, or update staff.", "pages/1_assistant.py", "Open Assistant", "nav_btn_asst")
nav_tile(row1_col2, "👤", "Employees", "Browse directory, onboard new employees, and manage profiles.", "pages/2_employees.py", "Manage Employees", "nav_btn_emp")
nav_tile(row1_col3, "📊", "Dashboard", "Workforce analytics, headcount distribution, and KPIs.", "pages/3_dashboard.py", "View Dashboard", "nav_btn_dash")
nav_tile(row1_col4, "📄", "Reports", "Export company roster and summaries to CSV, PDF, or Excel.", "pages/4_reports.py", "Export Reports", "nav_btn_rep")

st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
nav_tile(row2_col1, "💼", "Executive AI", "Candidate ranking, team builder, promotion & skill-gap analysis.", "pages/6_executive.py", "Executive Suite", "nav_btn_exec")
nav_tile(row2_col2, "🏆", "100 Benchmark", "Automated QA benchmark suite evaluating 100 enterprise queries.", "pages/8_benchmark_100.py", "Run Benchmark", "nav_btn_bm")
nav_tile(row2_col3, "🩺", "Diagnostics", "Verify Supabase DB connectivity, Groq LLM status, and test suite.", "pages/7_diagnostics.py", "Run Diagnostics", "nav_btn_diag")
nav_tile(row2_col4, "⚙️", "Settings", "Configure API keys, AI model fallback, and debug logs.", "pages/5_settings.py", "System Settings", "nav_btn_set")

st.markdown(
    '<div style="text-align:center;margin-top:2.5rem;color:#94A3B8;font-size:0.85rem;">'
    "💡 Tip: You can also use the left sidebar anytime to switch between sections."
    "</div>",
    unsafe_allow_html=True,
)
