"""
Enterprise HR AI Assistant v2.0 — Main entry point.

This is the welcome / home page. CSS is injected here and on every
child page via ``ui_helpers.load_css()``.
"""

import streamlit as st

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
    '<div style="padding:2rem 0;text-align:center;">'
    "<h1 style='color:#1A365D;font-size:2.2rem;margin-bottom:0.5rem;'>"
    "🤖 Enterprise HR AI Assistant</h1>"
    "<p style='color:#64748B;font-size:1.1rem;max-width:600px;margin:0 auto;'>"
    "Manage employees, ask questions about your workforce, "
    "view analytics dashboards, and generate reports — all in natural language."
    "</p>"
    "</div>",
    unsafe_allow_html=True,
)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        '<div class="card" style="text-align:center;">'
        '<div style="font-size:2rem;">💬</div>'
        "<h3>AI Assistant</h3>"
        "<p style='color:#64748B;font-size:0.85rem;'>Chat with AI to manage employees</p>"
        "</div>",
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        '<div class="card" style="text-align:center;">'
        '<div style="font-size:2rem;">👤</div>'
        "<h3>Employees</h3>"
        "<p style='color:#64748B;font-size:0.85rem;'>View and manage employee records</p>"
        "</div>",
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        '<div class="card" style="text-align:center;">'
        '<div style="font-size:2rem;">📊</div>'
        "<h3>Dashboard</h3>"
        "<p style='color:#64748B;font-size:0.85rem;'>Workforce analytics and trends</p>"
        "</div>",
        unsafe_allow_html=True,
    )

with col4:
    st.markdown(
        '<div class="card" style="text-align:center;">'
        '<div style="font-size:2rem;">📄</div>'
        "<h3>Reports</h3>"
        "<p style='color:#64748B;font-size:0.85rem;'>Export PDF, Excel, PowerPoint</p>"
        "</div>",
        unsafe_allow_html=True,
    )

st.markdown(
    '<div style="text-align:center;margin-top:2rem;color:#94A3B8;font-size:0.85rem;">'
    "Use the sidebar to navigate between sections."
    "</div>",
    unsafe_allow_html=True,
)
