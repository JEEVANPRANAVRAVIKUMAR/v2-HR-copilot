"""
Executive Decision Support page.

Provides one-click access to workforce agents and the planner for
executive-level questions without going through the chat interface.
"""

from __future__ import annotations

import streamlit as st
from ui_helpers import (
    load_css, render_sidebar, metric_card, info_card,
    empty_state, show_error,
)

st.set_page_config(
    page_title="🏢 Executive",
    page_icon="🏢",
    layout="wide",
)

load_css()
render_sidebar()

st.markdown(
    '<h2 style="color:#1A365D;margin:0 0 0.5rem;">🏢 Executive Decision Support</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="color:#64748B;margin:0 0 1rem;">'
    "Quick executive tools — promotions, transfers, attrition, "
    "team building, and workforce scorecard.</p>",
    unsafe_allow_html=True,
)

# ---- Lazy init ----
if "exec_initialized" not in st.session_state:
    st.session_state.exec_initialized = False


def init_workforce() -> bool:
    if st.session_state.exec_initialized:
        return True
    try:
        from config import get_settings
        from ai import GroqLLM, AnalyticsAgent, Planner, is_complex
        from database.queries import (
            EmployeeRepository, EmployeeHistoryRepository, AnalyticsRepository,
        )
        from database.client import DatabaseClient
        from services import EmployeeService, EmployeeHistoryService
        from services.workforce_agents import (
            PromotionAnalyzer, TransferAnalyzer, AttritionRisk,
            TeamBuilder, RecommendationEngine, SkillGapAgent, InsightAgent,
        )
        from utils.logger import get_logger

        settings = get_settings()
        logger = get_logger("executive_page")
        DatabaseClient.get_client()

        emp_repo = EmployeeRepository()
        history_repo = EmployeeHistoryRepository()
        analytics_repo = AnalyticsRepository()

        history_service = EmployeeHistoryService(history_repo, logger)
        employee_service = EmployeeService(
            repository=emp_repo, logger=logger, history_service=history_service,
        )
        llm = GroqLLM(
            api_key=settings.groq_api_key, model=settings.groq_model, logger=logger,
        )
        analytics_agent = AnalyticsAgent(analytics_repo, llm, logger)

        st.session_state.recommender = RecommendationEngine(
            employee_service, history_service, logger,
        )
        st.session_state.team_builder = TeamBuilder(
            st.session_state.recommender, logger,
        )
        st.session_state.promo_analyzer = PromotionAnalyzer(
            history_service, employee_service, logger,
        )
        st.session_state.transfer_analyzer = TransferAnalyzer(
            employee_service, history_service, analytics_agent, logger,
        )
        st.session_state.attrition_risk = AttritionRisk(
            history_service, employee_service, analytics_agent, logger,
        )
        st.session_state.skill_gap = SkillGapAgent(
            employee_service, analytics_agent, logger,
        )
        st.session_state.insight_agent = InsightAgent(
            analytics_agent, logger,
        )
        st.session_state.planner = Planner(llm, logger)

        st.session_state.exec_initialized = True
        return True
    except Exception as exc:
        st.error(f"Workforce services not available: {exc}")
        return False


# ---- Tabs ----
t1, t2, t3, t4, t5 = st.tabs([
    "📈 Promotions & Attrition",
    "🔄 Transfers",
    "👥 Team Builder",
    "💸 Skill Gap & Cost",
    "📊 Scorecard",
])

# ============================================================
# Tab 1: Promotions & Attrition
# ============================================================
with t1:
    st.markdown("<h4>Promotion Readiness</h4>", unsafe_allow_html=True)
    if st.button("Analyze Promotions", key="promo_btn", type="primary"):
        if init_workforce():
            with st.spinner("Analyzing..."):
                try:
                    results = st.session_state.promo_analyzer.analyze()
                    if not results:
                        st.info("No promotion candidates found.")
                    else:
                        for item in results[:8]:
                            exp = item.get("explanation")
                            st.markdown(
                                f"<div class='card'>"
                                f"<strong>{item['full_name']}</strong> "
                                f"— urgency {item['score']:.2f}"
                                + (" ⚠️ STALLED" if item.get("stalled") else "")
                                + "<br>"
                                + (exp.summary if exp and exp.summary else "")
                                + "</div>",
                                unsafe_allow_html=True,
                            )
                except Exception as exc:
                    show_error(str(exc))

    st.markdown("<h4>Attrition Risk</h4>", unsafe_allow_html=True)
    if st.button("Assess Attrition Risk", key="attr_btn", type="primary"):
        if init_workforce():
            with st.spinner("Analyzing..."):
                try:
                    results = st.session_state.attrition_risk.analyze()
                    if not results:
                        st.info("No elevated attrition risk detected.")
                    else:
                        high = [r for r in results if r["score"] > 0.3]
                        for item in high[:8]:
                            exp = item.get("explanation")
                            indicators = item.get("indicators", {})
                            flags = []
                            if indicators.get("stalled"):
                                flags.append("stalled")
                            if indicators.get("stagnant_role"):
                                flags.append("stagnant role")
                            if indicators.get("dept_churn"):
                                flags.append("dept churn")
                            if indicators.get("long_tenure"):
                                flags.append("long tenure")
                            st.markdown(
                                f"<div class='card'>"
                                f"<strong>{item['full_name']}</strong> "
                                f"— risk {item['score']:.2f} "
                                f"({' | '.join(flags)})<br>"
                                + (exp.summary if exp and exp.summary else "")
                                + "</div>",
                                unsafe_allow_html=True,
                            )
                except Exception as exc:
                    show_error(str(exc))

# ============================================================
# Tab 2: Transfers
# ============================================================
with t2:
    if st.button("Suggest Internal Transfers", key="trans_btn", type="primary"):
        if init_workforce():
            with st.spinner("Analyzing distribution..."):
                try:
                    results = st.session_state.transfer_analyzer.analyze()
                    if not results:
                        st.info("No transfer candidates identified.")
                    else:
                        for item in results[:8]:
                            exp = item.get("explanation")
                            st.markdown(
                                f"<div class='card'>"
                                f"<strong>{item['full_name']}</strong> "
                                f"({item.get('from_department','?')} → "
                                f"{item.get('to_department','?')}) "
                                f"— score {item['score']:.2f}<br>"
                                + (exp.summary if exp and exp.summary else "")
                                + "</div>",
                                unsafe_allow_html=True,
                            )
                except Exception as exc:
                    show_error(str(exc))

# ============================================================
# Tab 3: Team Builder
# ============================================================
with t3:
    st.markdown("<h4>Build a Team</h4>", unsafe_allow_html=True)
    team_brief = st.text_area(
        "Project brief",
        placeholder="e.g. Assemble a team for an AI healthcare project in Bangalore",
    )
    team_loc = st.text_input("Preferred location (optional)")
    if st.button("Build Team", key="team_btn", type="primary") and team_brief:
        if init_workforce():
            with st.spinner("Assembling team..."):
                try:
                    result = st.session_state.team_builder.build(
                        team_brief,
                        location=team_loc or None,
                    )
                    st.markdown(
                        f"<div class='card'><pre>{result['summary']}</pre></div>",
                        unsafe_allow_html=True,
                    )
                    for slot in result["slots"]:
                        c = slot["candidate"]
                        st.markdown(
                            f"<div class='card'>"
                            f"<strong>{slot['role']}</strong>: "
                            f"{c['full_name']} "
                            f"({c.get('department','?')} from {c.get('location','?')}) "
                            f"— score {slot['score']:.2f}</div>",
                            unsafe_allow_html=True,
                        )
                    if result["unfilled"]:
                        st.warning(
                            f"Unfilled roles: {', '.join(result['unfilled'])}"
                        )
                except Exception as exc:
                    show_error(str(exc))

# ============================================================
# Tab 4: Skill Gap & Cost
# ============================================================
with t4:
    st.markdown("<h4>Skill Gap Analysis</h4>", unsafe_allow_html=True)
    gap_target = st.text_input(
        "Target description",
        placeholder="e.g. New AI research centre in Hyderabad",
    )
    gap_growth = st.number_input(
        "Growth target % (optional)", value=0, step=5, min_value=0,
    )
    gap_roles = st.text_area(
        "Required roles (comma-separated, optional)",
        placeholder="e.g. ML Engineer, Data Scientist, Data Engineer",
    )
    if st.button("Analyze Gap", key="gap_btn", type="primary") and gap_target:
        if init_workforce():
            with st.spinner("Computing gap..."):
                try:
                    roles_list = (
                        [r.strip() for r in gap_roles.split(",") if r.strip()]
                        if gap_roles else None
                    )
                    growth_pct = gap_growth if gap_growth > 0 else None
                    result = st.session_state.skill_gap.analyze(
                        gap_target,
                        required_roles=roles_list,
                        growth_pct=growth_pct,
                    )
                    exp = result.get("explanation")
                    st.markdown(
                        f"<div class='card'>"
                        f"<h3>Skill Gap Report</h3>"
                        f"<p><strong>Target:</strong> {result['target']}</p>"
                        f"<p><strong>Current headcount:</strong> {result['current_headcount']}</p>"
                        f"<p><strong>Estimated hires:</strong> {result['estimated_hires']}</p>"
                        f"<p><strong>Est. cost:</strong> ${result['estimated_cost']:,.0f}</p>"
                        f"<p><strong>⚠️ Assumption:</strong> {result['cost_assumption']}</p>"
                        + (f"<p>{exp.summary}</p>" if exp and exp.summary else "")
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                except Exception as exc:
                    show_error(str(exc))

# ============================================================
# Tab 5: Workforce Scorecard
# ============================================================
with t5:
    if st.button("Load Scorecard", key="scorecard_btn", type="primary"):
        if init_workforce():
            with st.spinner("Loading..."):
                try:
                    result = st.session_state.insight_agent.full_scorecard()
                    col1, col2 = st.columns(2)
                    with col1:
                        metric_card(
                            "Total Headcount",
                            result.get("total_headcount", "N/A"),
                        )
                    with col2:
                        metric_card(
                            "Avg Tenure",
                            f"{result.get('avg_tenure_years', 0):.1f} yrs",
                        )

                    fastest = result.get("fastest_growing", {})
                    hub = result.get("largest_hub", {})
                    under = result.get("understaffed", {})
                    forecast = result.get("hiring_forecast", {})

                    st.markdown(
                        f"<div class='card'>"
                        f"<h3>Fastest Growing Department</h3>"
                        f"<p>{fastest.get('explanation').summary if fastest.get('explanation') else 'N/A'}</p>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div class='card'>"
                        f"<h3>Largest Engineering Hub</h3>"
                        f"<p>{hub.get('explanation').summary if hub.get('explanation') else 'N/A'}</p>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div class='card'>"
                        f"<h3>Understaffed</h3>"
                        f"<p>{under.get('explanation').summary if under.get('explanation') else 'None'}</p>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div class='card'>"
                        f"<h3>Hiring Forecast</h3>"
                        f"<p>{forecast.get('explanation').summary if forecast.get('explanation') else 'N/A'}</p>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                except Exception as exc:
                    show_error(str(exc))