"""
Shared UI components for Streamlit pages.

Every visual element used across multiple pages lives here so
the page files stay focused on logic.
"""

from __future__ import annotations

from typing import Any, List

import streamlit as st
import os

# Clean up duplicate diagnostics page to avoid Streamlit URL collision
try:
    if os.path.exists("pages/6_diagnostics.py"):
        os.remove("pages/6_diagnostics.py")
except Exception:
    pass


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


def _load_plotly():
    """Load Plotly only when a chart is actually requested.

    Chat, employee, settings, and report pages do not need Plotly at
    import time. Keeping charting optional prevents one missing optional
    package from crashing every Streamlit page during startup.
    """
    try:
        import plotly.express as px
        import plotly.graph_objects as go
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Charting is unavailable because Plotly is not installed. "
            "Install the application dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc
    return px, go


def bar_chart(
    data_frame,
    x: str,
    y: str,
    title: str = "",
    color: str | None = None,
) -> Any:
    """Render a Plotly bar chart with the app's styling."""
    px, _ = _load_plotly()
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
) -> Any:
    """Render a Plotly line chart for trends."""
    px, _ = _load_plotly()
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
) -> Any:
    """Render a donut chart for breakdowns (gender, status, etc.)."""
    _, go = _load_plotly()
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


def initialize_ai_session() -> bool:
    """Lazy-initialize AI components into st.session_state."""
    if st.session_state.get("chat_initialized", False):
        return True
    try:
        import logging
        from config import get_settings
        from ai import (
            GroqLLM, ConversationMemory, AIRouter, Planner, is_complex,
            SqlAgent, CrudAgent, SemanticSearchAgent, AnalyticsAgent,
            EmbeddingGenerator, HistoryAgent,
        )
        from database.queries import (
            EmployeeRepository, SqlQueryRepository,
            EmbeddingRepository, AnalyticsRepository,
            EmployeeHistoryRepository,
        )
        from database.client import DatabaseClient
        from services import EmployeeService, EmployeeHistoryService
        from services.workforce_agents import (
            RecommendationEngine, TeamBuilder, PromotionAnalyzer,
            TransferAnalyzer, AttritionRisk, SkillGapAgent, InsightAgent,
        )
        from utils.logger import get_logger

        settings = get_settings()
        logger = get_logger("assistant")

        # Force client initialization so repositories can be built.
        DatabaseClient.get_client()

        llm = GroqLLM(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            logger=logger,
        )

        # Repositories
        emp_repo = EmployeeRepository()
        history_repo = EmployeeHistoryRepository()
        sql_repo = SqlQueryRepository()
        embed_repo = EmbeddingRepository()
        analytics_repo = AnalyticsRepository()

        # Services
        history_service = EmployeeHistoryService(history_repo, logger)
        employee_service = EmployeeService(
            repository=emp_repo, logger=logger, history_service=history_service,
        )

        # Embedder for semantic search.
        embedder = EmbeddingGenerator(
            model_name=settings.embedding_model, logger=logger,
        )

        # Core agents.
        st.session_state.llm = llm
        st.session_state.memory = ConversationMemory()
        st.session_state.router = AIRouter(llm, logger)
        st.session_state.sql_agent = SqlAgent(llm, sql_repo, logger)
        st.session_state.crud_agent = CrudAgent(llm, employee_service, logger)
        st.session_state.semantic_agent = SemanticSearchAgent(
            embedder, embed_repo, llm, logger,
        )
        st.session_state.analytics_agent = AnalyticsAgent(
            analytics_repo, llm, logger,
        )
        st.session_state.history_agent = HistoryAgent(
            llm, history_service, employee_service, logger,
        )

        # Workforce agents.
        st.session_state.recommendation_engine = RecommendationEngine(
            employee_service, history_service, logger,
        )
        st.session_state.team_builder = TeamBuilder(
            st.session_state.recommendation_engine, logger,
        )
        st.session_state.promotion_analyzer = PromotionAnalyzer(
            history_service, employee_service, logger,
        )
        st.session_state.transfer_analyzer = TransferAnalyzer(
            employee_service, history_service,
            st.session_state.analytics_agent, logger,
        )
        st.session_state.attrition_risk = AttritionRisk(
            history_service, employee_service,
            st.session_state.analytics_agent, logger,
        )
        st.session_state.skill_gap_agent = SkillGapAgent(
            employee_service, st.session_state.analytics_agent, logger,
        )
        st.session_state.insight_agent = InsightAgent(
            st.session_state.analytics_agent, logger,
        )

        # Planner.
        st.session_state.planner = Planner(llm, logger)
        st.session_state.is_complex = is_complex

        st.session_state.chat_initialized = True
        return True

    except Exception as exc:
        import logging
        logging.getLogger("assistant").exception("AI initialization failed")
        st.session_state.init_error = str(exc)
        return False
