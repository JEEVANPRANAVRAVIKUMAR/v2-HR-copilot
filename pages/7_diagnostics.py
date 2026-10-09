"""
Diagnostics & Test Suite page — runs automated chatbot evaluation.
"""

from __future__ import annotations

import streamlit as st
import time
import json
from ui_helpers import load_css, render_sidebar, info_card
from ai_initializer import initialize_ai_session

st.set_page_config(
    page_title="🔍 Diagnostics",
    page_icon="🔍",
    layout="wide",
)

load_css()
render_sidebar()

st.markdown(
    '<h2 style="color:#1A365D;margin:0 0 0.5rem;">🔍 Chatbot Diagnostics</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="color:#64748B;margin:0 0 1.5rem;">'
    "Run the 25-question test suite to evaluate natural language routing, multi-agent planning, "
    "SQL translation, and career history aggregation.</p>",
    unsafe_allow_html=True,
)

# ---- Lazy Initialize AI ----
def init_ai_components() -> bool:
    success = initialize_ai_session()
    if not success:
        err = st.session_state.get("init_error", "Unknown initialization error")
        st.error(f"Failed to initialize AI components: {err}")
    return success

# ---- Questions List ----
DIAGNOSTIC_QUESTIONS = [
    "How many employees are in the database?",
    "List all employees in the AI department.",
    "Who are the managers?",
    "How many active employees are there?",
    "What is the average tenure of employees?",
    "Which department has the most employees?",
    "How many employees are in Chennai?",
    "Find a data scientist who knows machine learning.",
    "Who works with Python?",
    "Tell me about Rahul.",
    "Who has cloud database experience?",
    "Show details of employee EMP001",
    "Lookup Vikram Singh",
    "Who is Rahul Sharma?",
    "list everyone",
    "Show career history for EMP001",
    "When was EMP001 last promoted?",
    "Who has career stall for more than 4 years?",
    "Recommend data scientists in Chennai",
    "Build a team of 1 Data Analyst and 1 Manager for a FinTech project",
    "Who should we promote next?",
    "Suggest internal transfers for understaffed departments",
    "Who has high attrition risk?",
    "What are the skill gaps for our office?",
    "Recommend transfers to Engineering and find the skill gaps there."
]

if "diagnostics_results" not in st.session_state:
    st.session_state.diagnostics_results = None

if "diagnostics_running" not in st.session_state:
    st.session_state.diagnostics_running = False

def run_diagnostics():
    st.session_state.diagnostics_running = True
    results = []
    
    # Initialize components
    if not init_ai_components():
        st.session_state.diagnostics_running = False
        return

    # Dispatch logic
    def execute_query(user_message):
        try:
            import importlib
            assistant_mod = importlib.import_module("pages.1_assistant")
            return assistant_mod.dispatch_message(user_message)
        except Exception:
            # Fallback to local session state execution
            context = st.session_state.memory.get_context() if "memory" in st.session_state else []
            from ai.planner import is_complex
            
            if is_complex(user_message):
                agent_registry = {
                    "SQL": lambda msg, ctx, prev: st.session_state.sql_agent.answer(msg, context=ctx),
                    "Analytics": lambda msg, ctx, prev: st.session_state.analytics_agent.answer_question(msg),
                    "CRUD": lambda msg, ctx, prev: st.session_state.crud_agent.process(msg, context=ctx),
                    "SemanticSearch": lambda msg, ctx, prev: st.session_state.semantic_agent.answer(msg),
                    "History": lambda msg, ctx, prev: st.session_state.history_agent.answer(msg),
                    "Recommendation": lambda msg, ctx, prev: str(st.session_state.recommendation_engine.recommend()),
                    "TeamBuild": lambda msg, ctx, prev: st.session_state.team_builder.build(msg).get("summary", "No team summary"),
                    "Promotion": lambda msg, ctx, prev: str(st.session_state.promotion_analyzer.analyze()),
                    "Transfer": lambda msg, ctx, prev: str(st.session_state.transfer_analyzer.analyze()),
                    "Attrition": lambda msg, ctx, prev: str(st.session_state.attrition_risk.analyze()),
                    "SkillGap": lambda msg, ctx, prev: str(st.session_state.skill_gap_agent.analyze(msg)),
                    "Insights": lambda msg, ctx, prev: json.dumps(st.session_state.insight_agent.full_scorecard(), default=str),
                }
                res = st.session_state.planner.execute(user_message, agent_registry=agent_registry, context=context)
                return res.get("answer") or "Planner failed"

            decision = st.session_state.router.classify(user_message, context=context)
            intent = decision.intent.value

            tier1_map = {
                "SQL": lambda: st.session_state.sql_agent.answer(user_message, context=context),
                "CRUD": lambda: st.session_state.crud_agent.process(user_message, context=context),
                "SemanticSearch": lambda: st.session_state.semantic_agent.answer(user_message),
                "Analytics": lambda: st.session_state.analytics_agent.answer_question(user_message),
                "History": lambda: st.session_state.history_agent.answer(user_message),
                "Recommendation": lambda: str(st.session_state.recommendation_engine.recommend()),
                "TeamBuild": lambda: st.session_state.team_builder.build(user_message).get("summary", "No team summary"),
                "Promotion": lambda: str(st.session_state.promotion_analyzer.analyze()),
                "Transfer": lambda: str(st.session_state.transfer_analyzer.analyze()),
                "Attrition": lambda: str(st.session_state.attrition_risk.analyze()),
                "SkillGap": lambda: str(st.session_state.skill_gap_agent.analyze(user_message)),
                "Insights": lambda: json.dumps(st.session_state.insight_agent.full_scorecard(), default=str),
            }
            return tier1_map.get(intent, lambda: f"Unknown intent '{intent}'")()

    # Progress bar and status
    prog_bar = st.progress(0.0)
    status_text = st.empty()
    
    total = len(DIAGNOSTIC_QUESTIONS)
    for idx, question in enumerate(DIAGNOSTIC_QUESTIONS):
        status_text.markdown(f"**Executing Question {idx + 1}/{total}:** _{question}_")
        start_t = time.perf_counter()
        try:
            resp = execute_query(question)
            duration = time.perf_counter() - start_t
            results.append({
                "question": question,
                "status": "success",
                "response": resp,
                "duration": round(duration, 2)
            })
        except Exception as e:
            duration = time.perf_counter() - start_t
            results.append({
                "question": question,
                "status": "error",
                "error": str(e),
                "duration": round(duration, 2)
            })
            
        # Smoothly update progress
        prog_bar.progress((idx + 1) / total)
        
        # Inject small rate-limit prevention sleep
        time.sleep(3.0)

    # Save results
    st.session_state.diagnostics_results = results
    with open("chat_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
        
    st.session_state.diagnostics_running = False
    status_text.empty()
    prog_bar.empty()
    st.rerun()

# ---- UI Layout ----
col_btn, col_info = st.columns([1, 2])
with col_btn:
    if st.button("▶️ Run diagnostics Suite", use_container_width=True, disabled=st.session_state.diagnostics_running):
        run_diagnostics()

# Load previous results if file exists
if not st.session_state.diagnostics_results:
    try:
        with open("chat_test_results.json") as f:
            st.session_state.diagnostics_results = json.load(f)
    except Exception:
        pass

# Render results
if st.session_state.diagnostics_results:
    results = st.session_state.diagnostics_results
    passed = sum(1 for r in results if r.get("status") == "success")
    failed = len(results) - passed
    pass_rate = round((passed / len(results)) * 100, 1) if results else 0
    avg_time = round(sum(r.get("duration", 0) for r in results) / len(results), 2) if results else 0

    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Queries", len(results))
    with c2:
        st.metric("Passed Tests", passed, delta=None)
    with c3:
        st.metric("Failed Tests", failed, delta=None if failed == 0 else f"-{failed}", delta_color="inverse")
    with c4:
        st.metric("Avg Response Time", f"{avg_time}s")

    st.markdown("---")
    
    # Search and filters
    search_query = st.text_input("🔍 Search questions or answers", "").strip().lower()
    
    # Questions cards
    for idx, r in enumerate(results):
        q_text = r["question"]
        status = r["status"]
        
        # Apply search filter
        match_search = (
            not search_query 
            or search_query in q_text.lower() 
            or (status == "success" and search_query in str(r.get("response", "")).lower())
            or (status == "error" and search_query in str(r.get("error", "")).lower())
        )
        if not match_search:
            continue
            
        badge_style = (
            "background-color:#D1FAE5;color:#065F46;border:1px solid #A7F3D0;"
            if status == "success" else 
            "background-color:#FEE2E2;color:#991B1B;border:1px solid #FCA5A5;"
        )
        badge_text = "PASS" if status == "success" else "FAIL"
        
        with st.expander(f"Question {idx+1}: {q_text}", expanded=False):
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;">'
                f'<span style="padding:0.25rem 0.75rem;border-radius:9999px;font-size:0.75rem;font-weight:600;{badge_style}">{badge_text}</span>'
                f'<span style="color:#64748B;font-size:0.75rem;">Time: {r.get("duration", 0)}s</span>'
                f"</div>",
                unsafe_allow_html=True,
            )
            
            if status == "success":
                st.markdown(r.get("response", ""))
            else:
                st.error(f"Error: {r.get('error', 'Unknown execution error')}")
else:
    st.info("No diagnostic results found. Click the button above to run the evaluation suite.")
