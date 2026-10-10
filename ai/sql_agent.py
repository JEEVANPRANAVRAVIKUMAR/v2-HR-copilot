"""
SQL agent.

Takes a natural-language question and answers it by using the
appropriate service-layer APIs instead of raw SQL execution.
Because the Supabase REST API does not expose a raw SQL RPC,
the agent interprets the NL intent and dispatches to:
    - EmployeeService.search for filtered lookups
    - AnalyticsRepository / AnalyticsAgent for aggregates
    - Or a generic LLM fallback with available schema info.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from logging import Logger
from typing import Any, Dict, List

from database.queries import (
    AnalyticsRepository,
    EmployeeRepository,
    EmployeeHistoryRepository,
)
from database.queries.sql_query_repository import SqlQueryRepository
from utils.exceptions import ServiceError, SqlGenerationError

from .llm import GroqLLM

NATURAL_LANGUAGE_PROMPT = """\
You are an HR assistant. Using the provided data below, answer the user's \
question in clear, concise natural language.

User question: {question}

Available data (JSON):
{results}

Answer in 1-3 sentences. Be precise.
Guidelines:
1. If the data is empty (`[]` or `0`), state clearly that no employees or records were found matching the requested criteria (e.g. "No active employees in the AI department were found who joined after 2025."). Never say that the database is missing columns or lacks join dates.
2. If records are returned, accurately summarize the names, roles, departments, dates, or counts.
"""


class SqlAgent:
    """
    NL question → service-layer lookup → NL answer.

    Replaces raw SQL generation with client-builder-safe queries.
    """

    def __init__(
        self,
        llm: GroqLLM,
        sql_repo: SqlQueryRepository,
        logger: Logger,
    ) -> None:
        self._llm = llm
        self._sql_repo = sql_repo
        self._logger = logger
        self._emp_repo = EmployeeRepository()
        self._analytics_repo = AnalyticsRepository()
        self._history_repo = EmployeeHistoryRepository()

    def answer(
        self,
        question: str,
        *,
        context: List[Dict[str, str]] | None = None,
    ) -> str:
        """
        Answer a natural-language question using structured lookups.
        """
        start = time.perf_counter()
        op = "sql_agent.answer"

        try:
            schema = self._sql_repo.get_table_schema_hint()
            system_prompt = (
                "Generate one read-only SQL SELECT statement for the user's HR "
                "question. Use only the tables in this schema and no markdown.\n\n"
                f"{schema}"
            )
            raw_sql = ""
            try:
                messages = self._llm.build_messages(
                    system_prompt,
                    question,
                    context=context,
                )
                raw_sql = self._llm.generate(
                    messages, temperature=0.0, max_tokens=512,
                )
            except Exception as e:
                self._logger.warning("LLM SQL generation failed (%s), will use structured fallback.", e)

            sql = self._clean_sql(raw_sql) if raw_sql else ""
            
            rows = None
            try:
                if sql and "select" in sql.lower():
                    rows = self._sql_repo.execute(sql)
            except Exception as sql_err:
                self._logger.warning("Direct SQL query execution failed (%s), trying structured fallback.", sql_err)

            # ONLY run structured fallback if SQL translation raised an exception
            if rows is None:
                import re
                q_low = question.lower()
                dept_match = None
                for d in ["ai", "engineering", "sales", "hr", "marketing", "finance", "operations", "product"]:
                    if re.search(rf"\b{d}\b", q_low):
                        dept_match = d
                        break

                role_match = None
                for r in ["manager", "lead", "director", "developer", "engineer", "scientist", "analyst", "specialist", "intern"]:
                    if re.search(rf"\b{r}\b", q_low):
                        role_match = r
                        break

                active_filter = None
                if "inactive" in q_low:
                    active_filter = False
                elif "active" in q_low:
                    active_filter = True

                if dept_match or role_match or active_filter is not None:
                    matched_emps = self._emp_repo.search(
                        department=dept_match,
                        position_title=role_match,
                        is_active=active_filter,
                    )
                    rows = [
                        {
                            "employee_no": e.employee_no,
                            "full_name": e.full_name,
                            "department": e.department,
                            "position_title": e.position_title,
                            "is_active": e.is_active,
                            "email": e.email,
                            "work_location": e.work_location,
                            "joining_date": e.joining_date,
                        }
                        for e in matched_emps
                    ]
                else:
                    all_emps = self._emp_repo.search()
                    rows = [
                        {
                            "employee_no": e.employee_no,
                            "full_name": e.full_name,
                            "department": e.department,
                            "position_title": e.position_title,
                            "is_active": e.is_active,
                            "email": e.email,
                            "joining_date": e.joining_date,
                            "work_location": e.work_location,
                            "employment_type": e.employment_type,
                        }
                        for e in all_emps
                    ]

            try:
                answer = self._results_to_nl(question, rows, context=context)
            except Exception as nl_err:
                self._logger.warning("NL synthesis failed (%s), formatting rows directly.", nl_err)
                if not rows:
                    answer = f"No matching records found for query: '{question}'."
                else:
                    lines = []
                    for r in rows[:15]:
                        name = r.get("full_name") or r.get("name") or r.get("employee_no", "Unknown")
                        emp_no = r.get("employee_no", "")
                        dept = r.get("department") or r.get("department_name", "")
                        pos = r.get("position_title", "")
                        status = "Active" if r.get("is_active") else "Inactive"
                        details = " — ".join(filter(None, [pos, dept, status]))
                        lines.append(f"• **{name}** (`{emp_no}`) — {details}")
                    header = f"Found {len(rows)} matching record(s):\n\n"
                    answer = header + "\n".join(lines)

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info("%s | %.1fms | OK", op, duration_ms)
            return answer

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception("%s | %.1fms | ERROR: %s", op, duration_ms, exc)
            try:
                emps = self._emp_repo.search()
                lines = [f"• **{e.full_name}** (`{e.employee_no}`) — {e.position_title or 'N/A'} ({e.department or 'N/A'})" for e in emps[:10]]
                return f"Found {len(emps)} employees in the system:\n\n" + "\n".join(lines)
            except Exception:
                raise ServiceError(f"Failed to answer SQL question: {exc}") from exc

    @staticmethod
    def _clean_sql(sql: str) -> str:
        """Extract and clean the SELECT query from LLM output."""
        import re
        cleaned = sql.strip()
        if "```" in cleaned:
            match = re.search(r"```(?:sql)?\s*(SELECT[\s\S]*?)```", cleaned, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        select_match = re.search(r"\b(SELECT\b[\s\S]*?)(?:;|\Z)", cleaned, re.IGNORECASE)
        if select_match:
            return select_match.group(1).strip()
        return cleaned.strip()

    def _results_to_nl(
        self,
        question: str,
        rows: List[Dict[str, Any]],
        *,
        context: List[Dict[str, str]] | None = None,
    ) -> str:
        prompt = NATURAL_LANGUAGE_PROMPT.format(
            question=question,
            results=json.dumps(rows, indent=2, default=str),
        )
        messages = self._llm.build_messages(
            "You answer HR questions using only the supplied query results.",
            prompt,
            context=context,
        )
        return self._llm.generate(
            messages, temperature=0.2, max_tokens=512,
        ).strip()

    # Backward-compatible name used by older callers.
    def _to_nl(self, question: str, result: Dict[str, Any]) -> str:
        return self._results_to_nl(question, [result])

    # ----------------------------------------------------------------
    # Data handlers
    # ----------------------------------------------------------------

    def _handle_aggregate(self, question: str) -> Dict[str, Any]:
        try:
            snapshot = self._analytics_repo.full_snapshot()
            return {"type": "aggregate", "snapshot": snapshot}
        except Exception:
            return {"type": "error", "message": "Analytics data unavailable."}

    def _handle_tenure(self, question: str) -> Dict[str, Any]:
        try:
            avg = self._analytics_repo.average_tenure_years()
            dist = self._analytics_repo.tenure_distribution()
            return {"type": "tenure", "average_tenure_years": avg, "distribution": dist}
        except Exception:
            return {"type": "error", "message": "Tenure data unavailable."}

    def _handle_hiring(self, question: str) -> Dict[str, Any]:
        try:
            by_year = self._analytics_repo.hiring_by_year()
            by_month = self._analytics_repo.hiring_by_month()
            forecast = self._analytics_repo.hiring_forecast()
            return {"type": "hiring", "by_year": by_year, "by_month": by_month, "forecast": forecast}
        except Exception:
            return {"type": "error", "message": "Hiring data unavailable."}

    def _handle_diversity(self, question: str) -> Dict[str, Any]:
        try:
            by_gender = self._analytics_repo.gender_breakdown()
            return {"type": "diversity", "by_gender": by_gender}
        except Exception:
            return {"type": "error", "message": "Diversity data unavailable."}

    def _handle_status(self, question: str) -> Dict[str, Any]:
        try:
            by_status = self._analytics_repo.headcount_by_status()
            total = self._analytics_repo.total_headcount()
            return {"type": "status", "by_status": by_status, "total_headcount": total}
        except Exception:
            return {"type": "error", "message": "Status data unavailable."}

    def _handle_history(self, question: str) -> Dict[str, Any]:
        try:
            employees = self._emp_repo.get_all()
            stalled = []
            for emp in employees:
                events = self._history_repo.get_by_employee_no(emp.employee_no, limit=20)
                promoted_events = [e for e in events if e.event_type.value == "promoted" and e.occurred_at is not None]
                if promoted_events:
                    try:
                        last_promotion = promoted_events[0]
                        ts = last_promotion.occurred_at
                        if isinstance(ts, str):
                            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if ts.tzinfo is None:
                            from datetime import timezone
                            ts = ts.replace(tzinfo=timezone.utc)
                        days_since = (datetime.now(timezone.utc) - ts).days
                        if days_since > 1460:  # 4 years
                            stalled.append({"employee_no": emp.employee_no, "full_name": emp.full_name, "days_since_last_promotion": days_since})
                    except Exception:
                        pass
            return {"type": "history", "stalled_employees": stalled, "total": len(stalled)}
        except Exception:
            return {"type": "error", "message": "History data unavailable."}

    def _handle_city(self, question: str) -> Dict[str, Any]:
        try:
            hub = self._analytics_repo.largest_engineering_hub()
            return {"type": "city", "largest_hub": hub}
        except Exception:
            return {"type": "error", "message": "City data unavailable."}

    def _handle_department(self, question: str) -> Dict[str, Any]:
        try:
            by_dept = self._analytics_repo.headcount_by_department()
            understaffed = self._analytics_repo.understaffed_departments()
            fastest = self._analytics_repo.fastest_growing_department()
            return {"type": "department", "by_department": by_dept, "understaffed": understaffed, "fastest_growing": fastest}
        except Exception:
            return {"type": "error", "message": "Department data unavailable."}

    def _handle_salary_attr(self, question: str) -> Dict[str, Any]:
        try:
            employees = self._emp_repo.get_all()
            return {"type": "employee_list", "employees": [{"employee_no": e.employee_no, "full_name": e.full_name, "is_active": e.is_active} for e in employees]}
        except Exception:
            return {"type": "error", "message": "Employee data unavailable."}

    def _handle_search(self, question: str) -> Dict[str, Any]:
        try:
            employees = self._emp_repo.search(query=question)
            result = [{"employee_no": e.employee_no, "full_name": e.full_name, "is_active": e.is_active} for e in employees]
            return {"type": "search", "employees": result, "total": len(result)}
        except Exception:
            return {"type": "error", "message": "Search data unavailable."}

    # ----------------------------------------------------------------
    # NL formatting
    # ----------------------------------------------------------------

    def _fmt_nl(self, question: str, result: Dict[str, Any]) -> str:
        prompt = NATURAL_LANGUAGE_PROMPT.format(
            question=question,
            results=json.dumps(result, indent=2, default=str),
        )
        messages = [{"role": "user", "content": prompt}]
        try:
            return self._llm.generate(messages, temperature=0.2, max_tokens=512).strip()
        except Exception:
            return json.dumps(result, default=str)
