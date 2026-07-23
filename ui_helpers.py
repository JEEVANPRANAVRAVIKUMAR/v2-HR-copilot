"""
Shared UI components for Streamlit pages.

Every visual element used across multiple pages lives here so
the page files stay focused on logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ====================================================================
# Layout
# ====================================================================

PALETTE = {
    "navy": "#1A365D",
    "teal": "#0D9488",
    "amber": "#F59E0B",
    "surface": "#F1F5F9",
    "card": "#FFFFFF",
    "text": "#0F172A",
    "muted": "#64748B",
    "success": "#22C55E",
    "error": "#EF4444",
}

INTENT_COLORS = {
    "CRUD": ("#DBEAFE", "#1E40AF"),
    "SQL": ("#F3E8FF", "#7C3AED"),
    "Analytics": ("#FEF3C7", "#92400E"),
    "SemanticSearch": ("#D1FAE5", "#065F46"),
}


def load_css() -> None:
    """Inject custom CSS into the Streamlit app."""
    try:
        with open("assets/style.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass


# ====================================================================
# Sidebar
# ====================================================================

NAV_ITEMS = [
    ("Assistant", "💬", "1_assistant"),
    ("Employees", "👤", "2_employees"),
    ("Dashboard", "📊", "3_dashboard"),
    ("Reports", "📄", "4_reports"),
    ("Settings", "⚙️", "5_settings"),
]


def render_sidebar() -> None:
    """Render the branded sidebar header (pages are auto-discovered by Streamlit)."""
    with st.sidebar:
        st.markdown(
            '<div class="sidebar-header">'
            "<h2>🤖 HR AI Assistant</h2>"
            "<p>Enterprise v2.0</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")


# ====================================================================
# Cards
# ====================================================================


def metric_card(
    label: str,
    value: str | int | float,
    delta: str | None = None,
    help_text: str | None = None,
) -> None:
    """Render a KPI metric card using Streamlit's metric component."""
    st.metric(
        label=label,
        value=value,
        delta=delta,
        help=help_text,
    )


def info_card(title: str, body: str) -> None:
    """Render a simple info card."""
    st.markdown(
        f'<div class="card">'
        f"<h3>{title}</h3>"
        f"<p style='margin:0.25rem 0 0; color:#0F172A;'>{body}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ====================================================================
# Status badges
# ====================================================================


def status_badge(is_active: bool, status: str | None = None) -> str:
    """
    Return an HTML span for an employee's status.

    If ``status`` (from employment_details) is available it takes
    precedence; otherwise falls back to ``is_active``.
    """
    if status:
        css_class = status.lower().replace(" ", "-")
        label = status
    else:
        css_class = "active" if is_active else "inactive"
        label = "Active" if is_active else "Inactive"
    return f'<span class="status-badge {css_class}">{label}</span>'


# ====================================================================
# Charts
# ====================================================================


def bar_chart(
    data_frame,
    x: str,
    y: str,
    title: str = "",
    color: str | None = None,
) -> go.Figure:
    """Render a Plotly bar chart with the app's styling."""
    fig = px.bar(
        data_frame,
        x=x,
        y=y,
        title=title,
        color=color or x,
        color_discrete_sequence=[PALETTE["teal"], PALETTE["navy"]],
        text=y,
    )
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_color=PALETTE["text"],
        margin=dict(l=10, r=10, t=40, b=10),
        height=350,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#F1F5F9"),
        hovermode="x",
    )
    fig.update_traces(textposition="outside")
    return fig


def line_chart(
    data_frame,
    x: str,
    y: str,
    title: str = "",
) -> go.Figure:
    """Render a Plotly line chart for trends."""
    fig = px.line(
        data_frame,
        x=x,
        y=y,
        title=title,
        markers=True,
        color_discrete_sequence=[PALETTE["teal"]],
    )
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_color=PALETTE["text"],
        margin=dict(l=10, r=10, t=40, b=10),
        height=350,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#F1F5F9"),
    )
    return fig


def donut_chart(
    labels: List[str],
    values: List[int],
    title: str = "",
) -> go.Figure:
    """Render a donut chart for breakdowns (gender, status, etc.)."""
    colors = [PALETTE["teal"], PALETTE["navy"], PALETTE["amber"], "#94A3B8"]
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker=dict(colors=colors[: len(labels)]),
                textinfo="label+percent",
                textfont_size=13,
            )
        ]
    )
    fig.update_layout(
        title=title,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_color=PALETTE["text"],
        margin=dict(l=10, r=10, t=40, b=10),
        height=350,
        showlegend=False,
    )
    return fig


# ====================================================================
# Chat helpers
# ====================================================================


def render_chat_message(
    role: str,
    content: str,
    intent: str | None = None,
) -> None:
    """
    Render a chat message bubble using Streamlit's native chat
    components with custom styling applied via CSS classes.
    """
    with st.chat_message(role):
        st.markdown(content)
        if intent and role == "assistant":
            bg, fg = INTENT_COLORS.get(intent, ("#E2E8F0", "#64748B"))
            st.markdown(
                f'<span class="message-intent-tag" '
                f'style="background:{bg};color:{fg};">'
                f"🤖 {intent}</span>",
                unsafe_allow_html=True,
            )


# ====================================================================
# Empty / Loading states
# ====================================================================


def empty_state(icon: str, title: str, description: str) -> None:
    """Render a friendly empty-state placeholder."""
    st.markdown(
        f'<div style="text-align:center;padding:3rem 1rem;">'
        f'<div style="font-size:3rem;margin-bottom:0.5rem;">{icon}</div>'
        f'<h3 style="color:#0F172A;margin:0;">{title}</h3>'
        f'<p style="color:#64748B;margin:0.25rem 0 0;">{description}</p>'
        f"</div>",
        unsafe_allow_html=True,
    )


def loading_placeholder(key: str) -> Any:
    """Return a placeholder that can be replaced when data loads."""
    return st.empty()


# ====================================================================
# Error display
# ====================================================================


def show_error(message: str) -> None:
    """Display a user-friendly error message."""
    st.error(f"⚠️ {message}")
