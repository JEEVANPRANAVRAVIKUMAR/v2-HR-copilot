"""
AI Assistant page — conversational chat with two-tier intent routing.

Tier 1 (fast path): simple single-tool questions go straight to one
    agent (unchanged, Parts 1-5 dispatch).

Tier 2 (planner): complex multi-step questions are decomposed by the
    Planner into an ordered plan, executed across agents, and
    synthesised into one comprehensive answer.
"""

from __future__ import annotations

import logging
import streamlit as st
from ui_helpers import (
    load_css, render_sidebar, render_chat_message, empty_state,
)
from ai_initializer import initialize_ai_session

st.set_page_config(
    page_title="💬 Assistant",
    page_icon="💬",
    layout="wide",
)

load_css()
render_sidebar()

st.markdown(
    '<h2 style="color:#1A365D;margin:0 0 0.5rem;">💬 AI Assistant</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="color:#64748B;margin:0 0 1rem;">'
    "Ask me anything. Simple questions go straight to one tool; "
    "complex executive questions are decomposed, planned, and "
    "synthesised by the multi-agent planner.</p>",
    unsafe_allow_html=True,
)

# ---- Session state ----
if "messages" not in st.session_state:
    st.session_state.messages = []

if "chat_initialized" not in st.session_state:
    st.session_state.chat_initialized = False


def init_ai() -> bool:
    """Lazy-initialize AI components. Returns True on success."""
    return initialize_ai_session()


def _agent_registry() -> dict:
    """
    Build the planner agent registry — a dict that maps agent names
    to callable ``(msg, ctx, prev) -> str`` functions.
    """
    qa = st.session_state

    def _sql_fn(msg, ctx, prev):
        return qa.sql_agent.answer(msg, context=ctx)

    def _analytics_fn(msg, ctx, prev):
        return qa.analytics_agent.answer_question(msg)

    def _crud_fn(msg, ctx, prev):
        return qa.crud_agent.process(msg, context=ctx)

    def _semantic_fn(msg, ctx, prev):
        return qa.semantic_agent.answer(msg)

    def _history_fn(msg, ctx, prev):
        return qa.history_agent.answer(msg)

    def _recommendation_fn(msg, ctx, prev):
        # Extract key parameters from the message using simple heuristics.
        results = qa.recommendation_engine.recommend(
            role=_extract_role(msg),
            location=_extract_location(msg),
        )
        return _format_scored_list(results)

    def _teambuild_fn(msg, ctx, prev):
        r = qa.team_builder.build(msg)
        return (
            r.get("summary", "No team-building summary was returned.")
            if isinstance(r, dict)
            else str(r)
        )

    def _promotion_fn(msg, ctx, prev):
        r = qa.promotion_analyzer.analyze()
        return _format_scored_list(r)

    def _transfer_fn(msg, ctx, prev):
        r = qa.transfer_analyzer.analyze()
        return _format_scored_list(r)

    def _attrition_fn(msg, ctx, prev):
        r = qa.attrition_risk.analyze()
        return _format_scored_list(r, label="risk")

    def _skillgap_fn(msg, ctx, prev):
        r = qa.skill_gap_agent.analyze(msg)
        return _format_skill_gap(r)

    def _insights_fn(msg, ctx, prev):
        r = qa.insight_agent.full_scorecard()
        return json_dump_simple(r)

    return {
        "SQL": _sql_fn,
        "Analytics": _analytics_fn,
        "CRUD": _crud_fn,
        "SemanticSearch": _semantic_fn,
        "History": _history_fn,
        "Recommendation": _recommendation_fn,
        "TeamBuild": _teambuild_fn,
        "Promotion": _promotion_fn,
        "Transfer": _transfer_fn,
        "Attrition": _attrition_fn,
        "SkillGap": _skillgap_fn,
        "Insights": _insights_fn,
    }


def _resolve_contextual_employee_question(user_message: str, context: list) -> str | None:
    """
    If the user message refers to a previous employee using pronouns or implicit reference
    (e.g., 'He is recently hired right?', 'what is his salary/phone?', 'is she active?'),
    resolve the referenced employee from conversation history and synthesize an answer.
    """
    if not context:
        return None

    import re
    msg_low = user_message.lower()
    pronoun_patterns = [
        r"\b(he|she|they|him|her|his|their|this employee|that employee|the employee|this person|that person)\b",
        r"\b(recently hired|joined recently|new hire|still working|is active|what department|which department)\b",
    ]
    is_referential = any(re.search(p, msg_low) for p in pronoun_patterns)
    if not is_referential:
        return None

    # Find the most recently referenced employee in conversation history
    emp_no = None
    for turn in reversed(context):
        text = str(turn.get("content", ""))
        m = re.findall(r"\b(emp\d{1,6})\b", text, re.IGNORECASE)
        if m:
            emp_no = m[-1]
            break

    if not emp_no:
        return None

    service = getattr(st.session_state, "employee_service", None)
    llm = getattr(st.session_state, "llm", None)
    if not service or not llm:
        return None

    profile = service.get_full_profile(emp_no)
    if not profile:
        return None

    profile_summary = (
        f"Employee Number: {profile.employee_no}\n"
        f"Full Name: {profile.full_name}\n"
        f"Status: {'Active' if profile.is_active else 'Inactive'} ({profile.status or 'N/A'})\n"
        f"Department: {profile.department or 'N/A'}\n"
        f"Position Title: {profile.position_title or 'N/A'}\n"
        f"Employment Type: {profile.employment_type or 'N/A'}\n"
        f"Joining Date: {profile.joining_date or 'N/A'}\n"
        f"Work Location: {profile.work_location or 'N/A'}\n"
        f"Address: {profile.full_address or profile.city or 'N/A'}\n"
        f"Email: {profile.email or 'N/A'}\n"
        f"Phone: {profile.phone or 'N/A'}\n"
        f"DOB: {profile.dob or 'N/A'} | Gender: {profile.gender or 'N/A'}"
    )

    system_prompt = (
        "You are an HR Assistant. Answer the user's conversational question about the employee "
        "directly, politely, and accurately using ONLY the profile information below. "
        "Keep your response concise (1-3 sentences).\n\n"
        f"Current Employee Profile:\n{profile_summary}"
    )

    try:
        messages = llm.build_messages(
            system_prompt=system_prompt,
            user_message=user_message,
            context=context,
        )
        return llm.generate(messages, temperature=0.1, max_tokens=256).strip()
    except Exception:
        return None


def dispatch_message(user_message: str) -> str:
    """Route a user message — Tier 1 fast dispatch or Tier 2 planner."""
    memory = st.session_state.memory
    context = memory.get_context()
    router = st.session_state.router

    # ---- 1. Direct Greetings & Help Fast Path ----
    clean_msg = user_message.strip().lower().rstrip("!?. ")
    if clean_msg in {"hi", "hello", "hey", "hola", "namaste", "greetings", "good morning", "good afternoon", "good evening", "howdy", "sup"} or clean_msg in {"help", "what can you do", "who are you"}:
        response = (
            "👋 **Hello! I'm your Enterprise HR AI Assistant.**\n\n"
            "Here is what I can do for you:\n"
            "• **Employee Lookups & Details**: *'Who is Rahul Sharma'*, *'Details of EMP0100'*, *'Address of Neha Gupta'*\n"
            "• **Workforce Directory & Dates**: *'Show joining date of all employees'*, *'List active engineers in Chennai'*\n"
            "• **Workforce Analytics**: *'Headcount by department'*, *'Average tenure'*, *'Attrition risk indicators'*\n"
            "• **Career & Progression**: *'Show career timeline for EMP001'*, *'Who is ready for promotion?'*\n"
            "• **Talent & Planning**: *'Assemble a project team of 2 AI engineers'*, *'Recommend transfers to Engineering'*\n\n"
            "How can I assist you right now?"
        )
        memory.add_turn("assistant", response, intent="Greeting")
        return response

    # ---- 2. Contextual Pronoun / Reference Fast Path ----
    contextual_ans = _resolve_contextual_employee_question(user_message, context)
    if contextual_ans:
        memory.add_turn("assistant", contextual_ans, intent="CRUD")
        return contextual_ans

    # ---- 3. Complexity heuristic: if the message looks multi-step,
    #      override the router's single-intent classification. ----
    if st.session_state.is_complex(user_message):
        agent_map = _agent_registry()
        result = st.session_state.planner.execute(
            user_message,
            agent_registry=agent_map,
            context=context,
        )
        if result.get("complex") and result.get("answer"):
            plan_summary = ""
            if result.get("plan"):
                plan_summary = "\n\n---\n**Plan executed:**\n"
                for s in result["plan"]:
                    plan_summary += (
                        f"- Step {s.get('step', '?')}: **{s.get('agent', '?')}** → "
                        f"_{s.get('sub_question','?')}_\n"
                    )
            response = str(result["answer"]) + plan_summary
            memory.add_turn("assistant", response, intent="Planner")
            return response
        # Fall through: if planner returns empty, use Tier 1.

    # ---- Tier 1: single-agent dispatch ----
    decision = router.classify(user_message, context=context)
    intent = decision.intent.value

    # Tier 1 intent map.
    tier1_map = {
        "SQL": (
            lambda: st.session_state.sql_agent.answer(user_message, context=context)
        ),
        "CRUD": (
            lambda: st.session_state.crud_agent.process(user_message, context=context)
        ),
        "SemanticSearch": (
            lambda: st.session_state.semantic_agent.answer(user_message)
        ),
        "Analytics": (
            lambda: st.session_state.analytics_agent.answer_question(user_message)
        ),
        "History": (
            lambda: st.session_state.history_agent.answer(user_message)
        ),
        "Recommendation": (
            lambda: _format_scored_list(
                st.session_state.recommendation_engine.recommend(
                    role=_extract_role(user_message),
                    location=_extract_location(user_message),
                )
            )
        ),
        "TeamBuild": (
            lambda: st.session_state.team_builder.build(user_message)["summary"]
        ),
        "Promotion": (
            lambda: _format_scored_list(
                st.session_state.promotion_analyzer.analyze()
            )
        ),
        "Transfer": (
            lambda: _format_scored_list(
                st.session_state.transfer_analyzer.analyze()
            )
        ),
        "Attrition": (
            lambda: _format_scored_list(
                st.session_state.attrition_risk.analyze(), label="risk"
            )
        ),
        "SkillGap": (
            lambda: _format_skill_gap(
                st.session_state.skill_gap_agent.analyze(user_message)
            )
        ),
        "Insights": (
            lambda: json_dump_simple(
                st.session_state.insight_agent.full_scorecard()
            )
        ),
        "Planner": (
            # If the router itself classified as Planner despite not
            # passing is_complex, run the planner anyway.
            lambda: (
                lambda r: (
                    str(r.get("answer") or "Planner returned no answer.")
                    + (
                        "\n\n---\n**Plan executed:**\n"
                        + "\n".join(
                            f"- Step {s.get('step')}: **{s.get('agent')}** "
                            f"→ _{s.get('sub_question','?')}_"
                            for s in r.get("plan", [])
                        )
                        if r.get("plan")
                        else ""
                    )
                )
            )(st.session_state.planner.execute(
                user_message,
                agent_registry=_agent_registry(),
                context=context,
            ))
        ),
    }

    if intent in tier1_map:
        response = tier1_map[intent]()
    else:
        response = (
            "I'm not sure how to help with that. Try asking about "
            "employees, departments, career history, team building, "
            "promotions, transfers, or workforce insights."
        )

    memory.add_turn("assistant", response, intent=intent)
    return response


# ---- Helpers ----

def _extract_role(message: str) -> str:
    """Heuristic: extract a job-title-like phrase from the message."""
    lowered = message.lower()
    role_keywords = [
        "backend", "frontend", "devops", "qa", "data engineer",
        "data scientist", "ml engineer", "team lead", "product manager",
        "security engineer", "developer", "engineer",
    ]
    for rk in role_keywords:
        if rk in lowered:
            return rk.title()
    # Fallback: grab the first capitalised word that looks like a role.
    for tok in message.split():
        c = tok.strip(",.!?:;\"'")
        if len(c) >= 3 and c[0].isupper() and c.lower() not in {
            "the", "and", "for", "with", "from", "recommend",
            "show", "find", "give", "best", "new",
        }:
            return c
    return "Engineer"


def _extract_location(message: str) -> str | None:
    """Heuristic: look for a city-like word."""
    locations = [
        "chennai", "hyderabad", "pune", "bangalore", "mumbai", "delhi",
        "kolkata", "gurgaon", "noida", "ahmedabad",
        "san francisco", "new york", "london", "singapore",
        "berlin", "toronto", "tokyo",
    ]
    lowered = message.lower()
    for loc in locations:
        if loc in lowered:
            return loc.title()
    return None


def _format_scored_list(
    items: list,
    *,
    label: str = "score",
    top_n: int = 5,
) -> str:
    """Render a list of scored dicts into readable text."""
    if not items:
        return "No matching results."
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, (list, tuple)):
        return str(items)
    lines = []
    for item in items[:top_n]:
        if not isinstance(item, dict):
            lines.append(str(item))
            continue
        exp = item.get("explanation")
        score = item.get("score")
        try:
            score_text = f"{float(score):.2f}" if score is not None else ""
        except (TypeError, ValueError):
            score_text = str(score) if score not in (None, "") else ""
        name = item.get("full_name", "?")
        fallback = f"{name} ({score_text})" if score_text else str(name)
        summary = (
            exp.summary
            if exp and hasattr(exp, "summary") and exp.summary
            else (
                fallback
                if item.get("full_name")
                else str(item)
            )
        )
        lines.append(f"- {summary}")
    return "\n".join(lines)


def json_dump_simple(obj: dict) -> str:
    """Compact JSON-like summary of the insight scorecard."""
    import json
    # Build a compact summary dict, stripping the heavy explanation objects.
    obj = obj if isinstance(obj, dict) else {}

    def _section(name: str) -> dict:
        value = obj.get(name)
        return value if isinstance(value, dict) else {}

    forecast_data = _section("hiring_forecast").get("data")
    if not isinstance(forecast_data, dict):
        forecast_data = {}

    lite = {
        "headcount": obj.get("total_headcount"),
        "avg_tenure_years": obj.get("avg_tenure_years"),
        "fastest_growing": (
            _section("fastest_growing").get("data", [])[:1]
            if isinstance(_section("fastest_growing").get("data", []), list)
            else []
        ),
        "largest_hub": (
            _section("largest_hub").get("data", [])[:1]
            if isinstance(_section("largest_hub").get("data", []), list)
            else []
        ),
        "understaffed_count": len(
            _section("understaffed").get("data", [])
            if isinstance(_section("understaffed").get("data", []), list)
            else []
        ),
        "hiring_forecast_pct": forecast_data.get("projected_next_year_hires", 0),
    }
    return json.dumps(lite, indent=2, default=str)


def _format_currency(value: object) -> str:
    """Format optional numeric cost values without breaking a chat turn."""
    try:
        return f"${float(value or 0):,.0f}"
    except (TypeError, ValueError):
        return "$0"


def _format_skill_gap(result: object) -> str:
    """Render an optional skill-gap result without assuming model fields."""
    data = result if isinstance(result, dict) else {}
    return (
        f"Skill gap: {data.get('required_roles', [])} needed, "
        f"estimated {data.get('estimated_hires', 0)} hires "
        f"at {_format_currency(data.get('estimated_cost'))} "
        "(placeholder cost — NO salary data exists)."
    )


# ---- Render chat history ----
if not st.session_state.messages:
    empty_state(
        "💬",
        "Start a conversation",
        "Ask a simple question like 'Show me employees in Engineering' "
        "or a complex question like 'We're opening an AI research centre "
        "in Hyderabad — recommend transfers, find skill gaps, and "
        "estimate hiring cost.'",
    )
else:
    for msg in st.session_state.messages:
        render_chat_message(
            msg["role"],
            msg["content"],
            intent=msg.get("intent"),
        )

# ---- Chat input ----
if prompt := st.chat_input("Ask me anything about your workforce..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    render_chat_message("user", prompt)

    if init_ai():
        with st.spinner("Thinking..."):
            try:
                st.session_state.memory.add_turn("user", prompt)
                response = dispatch_message(prompt)
            except Exception as exc:
                logging.getLogger("assistant").exception("Chat dispatch failed")
                response = (
                    f"⚠️ **Error processing request:** {exc}\n\n"
                    "Please verify your query or check configuration."
                )

        st.session_state.messages.append(
            {"role": "assistant", "content": response}
        )
        st.rerun()
    else:
        err = st.session_state.get("init_error", "Unknown initialization error")
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": (
                    f"⚠️ **AI services are not available right now.**\n\n"
                    f"*Reason:* `{err}`\n\n"
                    "Please check your `.env` configuration (Groq API Key and Supabase credentials) and reload the page."
                ),
            }
        )
        st.rerun()
