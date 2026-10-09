"""
100-Query Enterprise Benchmark Page — Automated Senior QA Evaluation.
"""

from __future__ import annotations

import json
import time
import streamlit as st
from ui_helpers import load_css, render_sidebar, info_card
from ai_initializer import initialize_ai_session

TEST_CATEGORIES = {
    "1. Employee-Specific Queries": [
        "What department does Rahul Sharma work in?",
        "When did Rahul Sharma join the company?",
        "What is the current employment status of Rahul Sharma?",
        "Is Rahul Sharma currently an active employee?",
        "Can you pull up the HR record for Rahul Sharma?",
        "Find the department for Rahul Sharma.",
        "Tell me Rahul Sharma's exact joining date.",
        "Show me the basic employment details of Rahul Sharma.",
        "Did Rahul Sharma leave the company?",
        "Which team is Rahul Sharma assigned to?",
        "Check if Rahul Sharma is still working here.",
        "Get me the start date for Rahul Sharma.",
        "Is Rahul Sharma marked as active or inactive in the database?",
        "Pull the file on Rahul Sharma.",
        "Who is Rahul Sharma?",
        "Find an employee by the name of Rahul Sharma.",
        "What was Rahul Sharma's date of joining?",
        "Verify the employment status for Rahul Sharma.",
        "Does Rahul Sharma still work in the AI department?",
        "Show me all the information you have on Rahul Sharma.",
    ],
    "2. Department-Level Queries": [
        "How many employees are currently in the AI department?",
        "List all active employees in AI.",
        "Who works in the AI department?",
        "How many people are active in the AI team?",
        "Can you give me a list of everyone in AI?",
        "What is the total headcount for the AI department?",
        "Show me all inactive employees from the AI department.",
        "Are there any new joins in the AI department this month?",
        "Count the number of active staff in AI.",
        "Who are the members of the AI team?",
        "List the names of all employees in AI.",
        "Get the current headcount of the AI department.",
        "Which employees have left the AI department?",
        "Give me a department roster for AI.",
        "How many employees does the AI department have in total?",
        "Which department currently has the most active employees?",
        "List all departments we currently have in the system.",
        "How many distinct departments are recorded in the database?",
        "Show me the distribution of employees by department.",
        "Give me a breakdown of active versus inactive employees in AI.",
    ],
    "3. Tenure & Time-Based Queries": [
        "Who joined the company this month?",
        "How many employees were hired in 2023?",
        "List all employees who joined in January 2023.",
        "Who is our longest-serving active employee?",
        "Who is the newest employee in the company?",
        "Show me all employees who joined yesterday.",
        "How many people joined in the last 30 days?",
        "Which employees have their work anniversary this month?",
        "List all the hires from 2023.",
        "Who was hired between 2022-01-01 and 2023-12-31?",
        "How many new employees did we onboard last quarter?",
        "Find all employees who joined before 2023.",
        "Who joined the company after 2023-01-01?",
        "Show me the list of recent hires across all departments.",
        "Which active employees were hired in 2023?",
        "Give me the names of employees who joined exactly one year ago today.",
        "How many employees started this week?",
        "List everyone who joined on 2023-01-15.",
        "Are there any employees who joined before 2023 and are still active?",
        "Who was the first employee hired in the AI department?",
    ],
    "4. Status & Headcount Metrics": [
        "How many total active employees do we have right now?",
        "What is our overall company headcount?",
        "How many employees are currently marked as inactive?",
        "Give me a list of all inactive employees.",
        "How many people left the company this year?",
        "Show me all active employees in the system.",
        "What percentage of our workforce is currently active?",
        "Count the total number of inactive records in the database.",
        "Show me all employees who are not active anymore.",
        "How many active employees do we have compared to inactive?",
        "Filter the database to show only currently employed staff.",
        "How many employees resigned or were terminated in 2023?",
        "Get the total count of former employees.",
        "Check if there are any employees without a defined status.",
        "Can you list everyone whose status is active?",
        "Show me the ratio of active to inactive employees across the company.",
        "Give me a summary of current employee statuses.",
        "Are there any duplicate employee names in the database?",
        "How many active employees do we have in total across all departments?",
        "List all employees who are no longer with the company.",
    ],
    "5. Complex & Multi-Condition Queries": [
        "List all active employees in AI who joined after 2022.",
        "How many people from AI left the company in 2023?",
        "Who is the newest active employee in the AI department?",
        "Which department hired the most people in 2023?",
        "Show me all inactive employees from AI who joined before 2023.",
        "Find active employees who joined the AI department this month.",
        "List all employees in AI ordered by their joining date.",
        "Who is the longest-tenured active employee in the AI team?",
        "How many active staff hired in 2023 are in the AI department?",
        "Did anyone from AI join on 2023-01-15?",
        "Show me the joining dates of all active employees in AI.",
        "Sort all inactive employees by their joining date.",
        "Which active employees in AI have been here for more than 3 years?",
        "Are there any inactive employees who were hired this year?",
        "Show me a list of AI employees grouped by active and inactive status.",
        "Find all employees hired in January 2023 who are currently active.",
        "Which department has the highest number of inactive employees?",
        "List the top 5 most recent hires in the AI department.",
        "Show me all staff from AI and Engineering who joined last year.",
        "Give me a complete summary: total active employees, department breakdown, and recent hires this month.",
    ],
}

st.set_page_config(
    page_title="🏆 100 Benchmark Suite",
    page_icon="🏆",
    layout="wide",
)

load_css()
render_sidebar()

st.markdown(
    '<h2 style="color:#1A365D;margin:0 0 0.5rem;">🏆 100-Query Senior QA Benchmark Suite</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="color:#64748B;margin:0 0 1.5rem;">'
    "Systematic evaluation of 100 enterprise HR queries across employee-specific, "
    "department-level, time-based, headcount metrics, and complex multi-condition scenarios.</p>",
    unsafe_allow_html=True,
)

if "benchmark_results" not in st.session_state:
    st.session_state.benchmark_results = None

if "benchmark_running" not in st.session_state:
    st.session_state.benchmark_running = False

def run_benchmark():
    st.session_state.benchmark_running = True
    initialize_ai_session(force=True)
    
    import importlib
    asst_mod = importlib.import_module("pages.1_assistant")
    dispatch_message = asst_mod.dispatch_message

    suite_results = []
    all_queries = []
    for cat, qs in TEST_CATEGORIES.items():
        for q in qs:
            all_queries.append((cat, q))

    total = len(all_queries)
    prog_bar = st.progress(0.0)
    status_text = st.empty()

    passed_count = 0
    failed_count = 0

    for idx, (category, q) in enumerate(all_queries):
        status_text.markdown(f"**Running Test {idx + 1}/{total}** (`{category}`): _{q}_")
        start_t = time.perf_counter()
        status = "PASS"
        err = None
        response_text = ""

        try:
            response_text = dispatch_message(q)
            duration = round(time.perf_counter() - start_t, 2)
            low = (response_text or "").lower()
            if "⚠️ error processing request" in low or "crud operation failed" in low or "failed to answer" in low:
                status = "FAIL"
                err = response_text
                failed_count += 1
            else:
                passed_count += 1

        except Exception as exc:
            duration = round(time.perf_counter() - start_t, 2)
            status = "FAIL"
            err = str(exc)
            failed_count += 1

        suite_results.append({
            "id": idx + 1,
            "category": category,
            "query": q,
            "status": status,
            "duration": duration,
            "response": response_text,
            "error": err,
        })

        prog_bar.progress((idx + 1) / total)
        time.sleep(0.5)

    summary = {
        "total": total,
        "passed": passed_count,
        "failed": failed_count,
        "pass_rate": round((passed_count / total) * 100, 1),
        "results": suite_results,
    }

    st.session_state.benchmark_results = summary
    with open("test_100_results.json", "w") as f:
        json.dump(summary, f, indent=2)

    st.session_state.benchmark_running = False
    status_text.empty()
    prog_bar.empty()
    st.rerun()

col_btn, col_metric = st.columns([1, 2])
with col_btn:
    if st.button("▶️ Execute 100-Query Benchmark Suite", use_container_width=True, disabled=st.session_state.benchmark_running):
        run_benchmark()

# Load existing results if available
if not st.session_state.benchmark_results:
    try:
        with open("test_100_results.json") as f:
            st.session_state.benchmark_results = json.load(f)
    except Exception:
        pass

if st.session_state.benchmark_results:
    data = st.session_state.benchmark_results
    total = data.get("total", 100)
    passed = data.get("passed", 0)
    failed = data.get("failed", 0)
    pass_rate = data.get("pass_rate", 0)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Test Queries", total)
    with m2:
        st.metric("Passed Queries", passed)
    with m3:
        st.metric("Failed Queries", failed)
    with m4:
        st.metric("Pass Rate", f"{pass_rate}%")

    st.markdown("### 📋 Detailed Test Case Execution Breakdown")
    results = data.get("results", [])
    for r in results:
        badge = "🟢 PASS" if r["status"] == "PASS" else "🔴 FAIL"
        with st.expander(f"#{r['id']:03d} {badge} — {r['query']} ({r.get('duration', 0)}s)"):
            st.markdown(f"**Category:** `{r.get('category')}`")
            if r.get("error"):
                st.error(f"Error: {r['error']}")
            st.markdown(f"**Response:**\n\n{r.get('response')}")
