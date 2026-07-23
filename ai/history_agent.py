"""
History agent.

Wraps the EmployeeHistoryService timeline computation with name
resolution (so the user can ask "show me Rahul's history" without
knowing the employee number) and an LLM narration layer that turns
the raw timeline + career stats into plain English.

Also exposes ``find_stalled_employees`` — a non-LLM method used to
answer questions like "whose career has stalled for 4+ years?".
"""

from __future__ import annotations

import json
import time
from logging import Logger
from typing import Any, Dict, List

from ai.llm import GroqLLM
from models.history import (
    CareerStats,
    EmployeeTimeline,
    HistoryEventType,
    TimelineEntry,
)
from services import EmployeeService
from services.history_service import EmployeeHistoryService
from utils.exceptions import (
    EmployeeNotFoundError,
    HistoryError,
    LlmError,
    ServiceError,
)


HISTORY_NARRATION_PROMPT = """\
You are an HR analyst summarising an employee's career history. \
Below is the timeline of events and computed career statistics.

Employee: {employee_name} ({employee_no})

Timeline (chronological):
{timeline}

Career statistics:
{stats}

Write a concise, professional plain-English summary of this \
employee's career at the company. Cover:
- Total tenure at the company
- Career progression (promotions, role changes, transfers)
- Time in each role worth mentioning
- Time since last promotion and whether their progression has \
stalled (more than {stall_threshold_years} years without a promotion)
- Any other notable patterns

Write in clear paragraphs (no JSON, no markdown headings). Use \
2-5 sentences. Be factual. If any data is missing or zero, say so \
plainly.
"""


STALL_QUERY_PROMPT = """\
You are an HR assistant. The user asked a stalling-related question \
about employee careers. Below are the employees whose careers are \
currently stalled (no promotion in the last {threshold_years}+ \
years), with relevant career stats.

Stalled employees:
{employees}

Write a concise plain-English answer. List each employee, their \
tenure, when they were last promoted (or note "never promoted"), \
and the time since their last promotion. If no one is stalled, \
say so plainly. Use 1-4 sentences. Do not use JSON.
"""


class HistoryAgent:
    """
    Career timeline / stall-detection agent with LLM narration.
    """

    def __init__(
        self,
        llm: GroqLLM,
        history_service: EmployeeHistoryService,
        employee_service: EmployeeService,
        logger: Logger,
        *,
        default_stall_threshold_years: float = 4.0,
    ) -> None:
        self._llm = llm
        self._history = history_service
        self._employees = employee_service
        self._logger = logger
        self._default_stall_years = default_stall_threshold_years

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def answer(
        self,
        message: str,
        *,
        stall_threshold_years: float | None = None,
    ) -> str:
        """
        Answer a free-text history question with LLM narration.

        Roughly the flow:
            1. Resolve the employee to inspect.
               - If a name is mentioned, look them up via
                 EmployeeService.
               - If a question asks "whose career has stalled..."
                 calls :meth:`find_stalled_employees` narrates the
                 found list instead.
            2. Build the timeline + stats.
            3. LLM-narrate the result.

        Args:
            message: User's history question.
            stall_threshold_years: Optional override for stall
                detection; defaults to the agent default.

        Returns:
            Plain-English answer.
        """
        start = time.perf_counter()
        op = "history_agent.answer"

        try:
            threshold = (
                stall_threshold_years
                if stall_threshold_years is not None
                else self._default_stall_years
            )

            # Stall detection: questions like "whose career has
            # stalled..." have no single employee target.
            lowered = message.lower()
            stall_keywords = (
                "stalled", "stalling", "stall ", "no promotion",
                "hasn't been promoted", "has not been promoted",
                "no one been promoted", "career path",
            )
            if any(k in lowered for k in stall_keywords) and not _names_in_message(message):
                return self._narrate_stalled(threshold)
            if any(k in lowered for k in stall_keywords) and "who" in lowered:
                # "Who has stalled..." — even if a name slipped in,
                # treat as a stall query.
                return self._narrate_stalled(threshold)

            # Otherwise: find a named employee and narrate their timeline.
            employee_no, full_name = self._resolve_employee(message)
            if not employee_no:
                return (
                    "I couldn't find an employee mentioned in your "
                    "question. Try including the employee's name or "
                    "number (e.g. 'Show me Rahul's history')."
                )

            timeline = self._history.build_timeline(
                employee_no,
                full_name=full_name,
                stall_threshold_days=threshold * 365.0,
            )
            narration = self._narrate_timeline(timeline, threshold)

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | emp=%s | stalled=%s | %.1fms | OK",
                op, employee_no, timeline.stats.is_stalled, duration_ms,
            )
            return narration

        except (EmployeeNotFoundError, HistoryError):
            raise
        except LlmError:
            raise ServiceError("LLM narration failed.") from None
        except ServiceError:
            raise
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR: %s", op, duration_ms, exc,
            )
            raise ServiceError("Failed to answer history question.") from exc

    def build_timeline(
        self,
        employee_no: str,
        *,
        stall_threshold_years: float | None = None,
    ) -> EmployeeTimeline:
        """
        Build (and return) the timeline for a specific employee
        without LLM narration.

        Useful for the UI/Streamlit page that wants the structured
        data without spending an LLM call.
        """
        threshold = (
            stall_threshold_years
            if stall_threshold_years is not None
            else self._default_stall_years
        )
        return self._history.build_timeline(
            employee_no,
            stall_threshold_days=threshold * 365.0,
        )

    def find_stalled_employees(
        self,
        *,
        threshold_years: float | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Return all employees whose careers are stalled.

        The returned list contains, for each stalled employee:
            - employee_no
            - full_name
            - total_tenure_days
            - promotions_count
            - time_since_last_promotion_days
            - is_stalled (always True; included for convenience)
            - timeline (full EmployeeTimeline dict)

        Args:
            threshold_years: Stall threshold; default agent default.

        Returns:
            List of stalled-employee dicts, ordered by time since
            last promotion descending (most-stalled first).
        """
        start = time.perf_counter()
        op = "history_agent.find_stalled_employees"
        threshold_years = (
            threshold_years
            if threshold_years is not None
            else self._default_stall_years
        )
        threshold_days = threshold_years * 365.0

        try:
            # Walk every employee, build timeline, keep stalled ones.
            employees = self._employees.list_all_employees()
            stalled: List[Dict[str, Any]] = []
            for emp in employees:
                timeline = self._history.build_timeline(
                    emp.employee_no,
                    full_name=emp.full_name,
                    stall_threshold_days=threshold_days,
                )
                if timeline.stats.is_stalled:
                    stalled.append(_stall_dict(emp, timeline))

            # Sort by time_since_last_promotion_days desc.
            stalled.sort(
                key=lambda d: (
                    d.get("time_since_last_promotion_days")
                    if d.get("time_since_last_promotion_days") is not None
                    else float("inf")
                ),
                reverse=True,
            )

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | stalled=%d/%d | threshold=%.1fyr | %.1fms | OK",
                op, len(stalled), len(employees), threshold_years,
                duration_ms,
            )
            return stalled

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR: %s", op, duration_ms, exc,
            )
            raise ServiceError(
                "Failed to detect stalled careers.",
            ) from exc

    # ----------------------------------------------------------------
    # Internal
    # ----------------------------------------------------------------

    def _resolve_employee(self, message: str) -> tuple[str | None, str | None]:
        """
        Look for a direct employee number, else search by name.
        """
        # Direct EMP### style employee number?
        upper = message.upper()
        # Replace punctuation with spaces so we get clean tokens
        # (e.g. "EMP005's" -> "EMP005 S").
        cleaned_msg = "".join(
            c if c.isalnum() or c.isspace() else " " for c in upper
        )
        tokens = cleaned_msg.split()
        for tok in tokens:
            if tok.startswith("EMP") and any(c.isdigit() for c in tok):
                emp = self._employees.get_employee_by_no(tok)
                if emp:
                    return emp.employee_no, emp.full_name

        # Otherwise: try matching candidate name substrings.
        candidates = _extract_names(message)
        for name in candidates:
            results = self._employees.search_employees(query=name)
            if results:
                # Pick the first matching one (best effort — the UI
                # can present disambiguation later).
                first = results[0]
                return first.employee_no, first.full_name

        return None, None

    def _narrate_timeline(
        self,
        timeline: EmployeeTimeline,
        stall_threshold_years: float,
    ) -> str:
        """
        Send the timeline + stats to the LLM for narration.
        """
        prompt = HISTORY_NARRATION_PROMPT.format(
            employee_name=timeline.full_name or "(unknown)",
            employee_no=timeline.employee_no,
            timeline=_format_timeline_for_prompt(timeline.events),
            stats=_format_stats_for_prompt(timeline.stats),
            stall_threshold_years=stall_threshold_years,
        )
        messages = [{"role": "user", "content": prompt}]
        return self._llm.generate(
            messages, temperature=0.2, max_tokens=512,
        ).strip()

    def _narrate_stalled(
        self,
        stall_threshold_years: float,
    ) -> str:
        """
        Narrate the stalled-employees list.
        """
        stalled = self.find_stalled_employees(
            threshold_years=stall_threshold_years,
        )
        payload = [
            {
                "employee_no": s["employee_no"],
                "full_name": s["full_name"],
                "tenure_days": s["total_tenure_days"],
                "promotions_count": s["promotions_count"],
                "time_since_last_promotion_days": s["time_since_last_promotion_days"],
            }
            for s in stalled
        ]
        prompt = STALL_QUERY_PROMPT.format(
            threshold_years=stall_threshold_years,
            employees=json.dumps(payload, indent=2, default=str),
        )
        if not stalled:
            return (
                f"No employees are currently stalled "
                f"(threshold: {stall_threshold_years}+ years without "
                f"a promotion)."
            )
        return self._llm.generate(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=512,
        ).strip()


# =====================================================================
# Module-level helpers
# =====================================================================


def _names_in_message(message: str) -> bool:
    """
    Heuristic: are there any capitalized words in the message that
    might be a name? Used to decide between per-employee and stall
    queries.
    """
    for tok in message.split():
        # Strip punctuation
        cleaned = "".join(c for c in tok if c.isalpha())
        if cleaned and cleaned[0].isupper() and cleaned.lower() not in {
            "show", "me", "history", "career", "who", "whose",
            "the", "for", "of", "is", "has", "been", "was", "and",
            "or", "with", "from", "to", "at", "in", "on", "by",
        }:
            return True
    return False


def _extract_names(message: str) -> List[str]:
    """
    Extract candidate names (capitalized sequences) from a message.
    Lowercases known stop words. Returns at most a couple of
    candidates to bound the search cost.
    """
    stop_words = {
        "show", "me", "history", "career", "who", "whose", "the",
        "for", "of", "is", "has", "been", "was", "and", "or",
        "with", "from", "to", "at", "in", "on", "by", "stalled",
        "stalling", "promotion", "promoted", "years", "year",
        "ago", "since", "last", "tell", "give", "what", "summary",
    }
    candidates: List[str] = []
    for tok in message.split():
        cleaned = "".join(
            c for c in tok if c.isalpha() or c.isspace()
        ).strip()
        if not cleaned:
            continue
        if cleaned[0].isupper() and cleaned.lower() not in stop_words:
            if len(cleaned) >= 2:
                candidates.append(cleaned)
    return candidates[:3]


def _format_timeline_for_prompt(events: List[TimelineEntry]) -> str:
    """
    Render events as plain text for the LLM.
    """
    if not events:
        return "(no events recorded)"
    lines = []
    for e in events:
        ts = e.occurred_at.strftime("%Y-%m-%d")
        parts = [ts, e.event_type.value]
        if e.from_value or e.to_value:
            parts.append(
                f"{e.from_value or '-'} -> {e.to_value or '-'}"
            )
        if e.note:
            parts.append(f"({e.note})")
        lines.append(" - " + " | ".join(parts))
    return "\n".join(lines)


def _format_stats_for_prompt(stats: CareerStats) -> str:
    """
    Render CareerStats as indented text for the LLM.
    """
    role_lines = []
    for role, days in stats.time_in_each_role.items():
        years = days / 365.0
        role_lines.append(
            f"  - {role}: {days:.0f} days ({years:.1f} years)"
        )
    roles_str = "\n".join(role_lines) if role_lines else "  (none)"
    last_promo = (
        f"{stats.time_since_last_promotion_days:.0f} days "
        f"({stats.time_since_last_promotion_days / 365.0:.1f} years)"
        if stats.time_since_last_promotion_days is not None
        else "never promoted"
    )
    avg_between = (
        f"{stats.average_time_between_promotions_days:.0f} days"
        if stats.average_time_between_promotions_days is not None
        else "n/a"
    )
    return (
        f"Total tenure: {stats.total_tenure_days:.0f} days "
        f"({stats.total_tenure_days / 365.0:.1f} years)\n"
        f"Promotions: {stats.promotions_count}\n"
        f"Time since last promotion: {last_promo}\n"
        f"Average time between promotions: {avg_between}\n"
        f"Currently stalled: {stats.is_stalled}\n"
        f"Stall threshold: {stats.stall_threshold_days:.0f} days\n"
        f"Time in each role:\n{roles_str}"
    )


def _stall_dict(emp, timeline: EmployeeTimeline) -> Dict[str, Any]:
    """
    Compose the per-employee stalled summary dict.
    """
    return {
        "employee_no": emp.employee_no,
        "full_name": emp.full_name,
        "total_tenure_days": timeline.stats.total_tenure_days,
        "promotions_count": timeline.stats.promotions_count,
        "time_since_last_promotion_days": (
            timeline.stats.time_since_last_promotion_days
        ),
        "is_stalled": True,
        "timeline": timeline.model_dump(),
    }
