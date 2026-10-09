"""
Analytics agent.

Computes workforce statistics (headcount, hiring trends, tenure,
diversity) through the AnalyticsRepository and returns BOTH raw
data (ready for charting) and an LLM-written plain-English
explanation.
"""

from __future__ import annotations

import json
import time
from logging import Logger
from typing import Any, Dict, List

from database.queries import AnalyticsRepository
from utils.exceptions import LlmError, ServiceError

from .llm import GroqLLM

ANALYTICS_EXPLANATION_PROMPT = """\
You are an HR data analyst. Below is a workforce analytics \
snapshot in JSON. Write a concise 2-5 sentence summary in \
plain English, highlighting key numbers and trends.

Data:
{data}

Write in a professional, factual tone. Do not add speculation.
"""

ANALYTICS_QUERY_PROMPT = """\
You are an HR data analyst. The user asked a question about \
workforce analytics.

Question: {question}

Available metrics and dimensions: headcount (total/by department/\
by status), hiring trends (by year/by month), tenure (average/\
distribution), diversity (gender breakdown).

Based on the question, which of the following metrics should be \
queried? Return a JSON list of metric names:
["total_headcount", "by_department", "by_status", "by_gender", \
"hiring_by_year", "hiring_by_month", "average_tenure_years", \
"tenure_distribution"]

Example: If the user asks "How diverse is the company?" respond with \
["by_gender"].

Only include metrics that are relevant. Return ONLY the JSON array.
"""


class AnalyticsAgent:
    """
    Workforce analytics agent.

    Provides structured data and natural-language summaries
    for hiring trends, headcount, tenure, and diversity.
    """

    def __init__(
        self,
        analytics_repo: AnalyticsRepository,
        llm: GroqLLM,
        logger: Logger,
    ) -> None:
        self._repo = analytics_repo
        self._llm = llm
        self._logger = logger

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def full_snapshot(self) -> Dict[str, Any]:
        """
        Return all analytics metrics as a single dict (no NL).

        Returns:
            Dict ready for charting: total_headcount, by_department,
            by_status, by_gender, hiring_by_year, hiring_by_month,
            average_tenure_years, tenure_distribution.
        """
        start = time.perf_counter()
        op = "analytics_agent.full_snapshot"

        try:
            data = self._repo.full_snapshot()

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | %.1fms | OK", op, duration_ms,
            )
            return data

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR", op, duration_ms,
            )
            raise ServiceError(
                "Failed to retrieve analytics data."
            ) from exc

    def insight_snapshot(self) -> Dict[str, Any]:
        """
        Return the enhanced insight snapshot (including
        fastest_growing_department, largest_engineering_hub,
        understaffed_departments, hiring_forecast).
        """
        start = time.perf_counter()
        op = "analytics_agent.insight_snapshot"
        try:
            data = self._repo.insight_snapshot()
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info("%s | %.1fms | OK", op, duration_ms)
            return data
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception("%s | %.1fms | ERROR", op, duration_ms)
            raise ServiceError("Failed to retrieve insight snapshot.") from exc

    def explain_snapshot(self) -> str:
        """
        Return an LLM-written plain-English summary of all metrics.

        Returns:
            Natural-language summary.
        """
        start = time.perf_counter()
        op = "analytics_agent.explain_snapshot"

        try:
            data = self._repo.full_snapshot()
            prompt = ANALYTICS_EXPLANATION_PROMPT.format(
                data=json.dumps(data, indent=2, default=str),
            )
            explanation = self._llm.generate(
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=512,
            ).strip()

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | %.1fms | OK", op, duration_ms,
            )
            return explanation

        except (LlmError, ServiceError):
            raise

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR", op, duration_ms,
            )
            raise ServiceError(
                "Failed to generate analytics explanation."
            ) from exc

    def answer_question(self, question: str) -> str:
        """
        Answer a specific analytics question.

        The agent selects which metrics to query based on the
        question, fetches them, and returns a summary.

        Args:
            question: User's analytics question.

        Returns:
            NL answer with relevant numbers.
        """
        start = time.perf_counter()
        op = "analytics_agent.answer_question"

        try:
            # Determine which metrics to query
            metric_selection = self._select_metrics(question)
            if not isinstance(metric_selection, list):
                metric_selection = ["total_headcount"]

            # Fetch selected metrics
            snapshot = self._repo.full_snapshot()
            selected = {
                k: snapshot[k]
                for k in metric_selection
                if k in snapshot
            }

            # Generate explanation
            prompt = ANALYTICS_EXPLANATION_PROMPT.format(
                data=json.dumps(selected, indent=2, default=str),
            )
            answer = self._llm.generate(
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=512,
            ).strip()

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | question='%s' | metrics=%s | %.1fms | OK",
                op, question, metric_selection, duration_ms,
            )
            return answer

        except (LlmError, ServiceError, Exception) as exc:
            self._logger.warning("Analytics LLM explanation failed (%s), returning formatted metrics directly.", exc)
            try:
                snapshot = self._repo.full_snapshot()
                total = snapshot.get("total_headcount", 0)
                by_dept = snapshot.get("by_department", {})
                dept_summary = ", ".join(f"{d}: {c}" for d, c in list(by_dept.items())[:6])
                return (
                    f"**Workforce Analytics Snapshot:**\n\n"
                    f"• **Total Headcount:** {total}\n"
                    f"• **Departments:** {dept_summary}\n"
                    f"• **Average Tenure:** {snapshot.get('average_tenure_years', 0):.1f} years\n"
                    f"• **Active Status:** {snapshot.get('by_status', {}).get('Active', total)} active"
                )
            except Exception:
                raise ServiceError(f"Failed to answer analytics question: {exc}") from exc

    # ----------------------------------------------------------------
    # Internal
    # ----------------------------------------------------------------

    def _select_metrics(self, question: str) -> List[str]:
        """
        Use the LLM to determine which metrics are relevant.
        """
        prompt = ANALYTICS_QUERY_PROMPT.format(question=question)
        raw = self._llm.generate(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=256,
        ).strip()

        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return ["total_headcount"]
