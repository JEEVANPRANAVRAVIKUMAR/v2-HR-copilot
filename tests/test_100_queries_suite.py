"""
Senior QA Automation Test Suite: 100 Enterprise HR Test Queries
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai_initializer import initialize_ai_session
import streamlit as st

# Define the 100 benchmark queries categorized
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


def run_full_suite() -> Dict[str, Any]:
    print("=" * 70)
    print("STARTING 100-QUERY SENIOR QA TEST SUITE")
    print("=" * 70)

    # Initialize AI components
    success = initialize_ai_session(force=True)
    if not success:
        print("ERROR: Failed to initialize AI session.")
        return {"error": "Initialization failed"}

    import importlib
    asst_mod = importlib.import_module("pages.1_assistant")
    dispatch_message = asst_mod.dispatch_message

    suite_results: List[Dict[str, Any]] = []
    category_metrics: Dict[str, Dict[str, int]] = {}

    query_count = 0
    total_passed = 0
    total_failed = 0
    total_warnings = 0

    for category, queries in TEST_CATEGORIES.items():
        print(f"\n--- Running Category: {category} ({len(queries)} queries) ---")
        category_metrics[category] = {"total": len(queries), "passed": 0, "failed": 0, "warnings": 0}

        for q in queries:
            query_count += 1
            start_t = time.perf_counter()
            status = "PASS"
            error_msg = None
            response = ""

            try:
                # Dispatch query
                response = dispatch_message(q)
                duration = time.perf_counter() - start_t

                # Validation checks on response quality
                low_resp = (response or "").lower()
                if "error" in low_resp or "sorry, i couldn't complete" in low_resp or "failed to answer" in low_resp:
                    status = "FAIL"
                    error_msg = response
                    total_failed += 1
                    category_metrics[category]["failed"] += 1
                elif "no matching" in low_resp or "0" in low_resp or "unknown" in low_resp:
                    # Valid negative response or possible warning
                    status = "PASS"
                    total_passed += 1
                    category_metrics[category]["passed"] += 1
                else:
                    status = "PASS"
                    total_passed += 1
                    category_metrics[category]["passed"] += 1

            except Exception as exc:
                duration = time.perf_counter() - start_t
                status = "FAIL"
                error_msg = str(exc)
                total_failed += 1
                category_metrics[category]["failed"] += 1

            record = {
                "id": query_count,
                "category": category,
                "query": q,
                "status": status,
                "duration_seconds": round(duration, 3),
                "response": response[:300] if response else None,
                "error": error_msg,
            }
            suite_results.append(record)
            print(f"[{query_count:03d}/100] [{status}] {q[:50]:<50} ({round(duration, 2)}s)")
            if error_msg:
                print(f"    -> ERROR: {error_msg}")

            # Politeness delay between LLM calls
            time.sleep(1.0)

    summary = {
        "total_queries": query_count,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_warnings": total_warnings,
        "pass_rate_percentage": round((total_passed / query_count) * 100, 1) if query_count else 0,
        "category_metrics": category_metrics,
        "results": suite_results,
    }

    with open("test_100_results.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 70)
    print(f"SUITE COMPLETE: {total_passed}/{query_count} PASSED ({summary['pass_rate_percentage']}%)")
    print("=" * 70)
    return summary


if __name__ == "__main__":
    run_full_suite()
