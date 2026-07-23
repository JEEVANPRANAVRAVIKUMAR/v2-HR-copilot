"""
Part 6 Workforce agents.

Every agent here produces SCORED, EXPLAINABLE output — each
returned recommendation or result carries an :class:`Explanation`
with an overall score and itemized reasons.

Agents:
    - RecommendationEngine   (rank candidates for a role + location)
    - TeamBuilder            (assemble multi-role team from one brief)
    - PromotionAnalyzer      (rank who is due for promotion)
    - TransferAnalyzer       (suggest internal moves)
    - AttritionRisk          (flag risk indicators)
    - SkillGapAgent          (identify missing skills vs required)
    - InsightAgent           (history-backed workforce scorecard)

All agents work through EmployeeService / EmployeeHistoryService /
AnalyticsAgent — never touch the database directly.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from logging import Logger
from typing import Any, Dict, List, Optional

from models.employee import Employee
from models.history import (
    CareerStats,
    EmployeeTimeline,
    Explanation,
    ExplanationReason,
    HistoryEventType,
)
from utils.exceptions import ServiceError


# Maximum number of output items per agent call.
DEFAULT_MAX_RESULTS = 10

# Default wrapper budget (hiring cost estimate) — we use a placeholder
# because salary data does NOT exist in the current schema. Every
# consumer MUST state this assumption clearly.
_PLACEHOLDER_HIRE_COST = 60_000.0
_PLACEHOLDER_MONTHS = 6


# =====================================================================
# 1. Recommendation Engine
# =====================================================================


class RecommendationEngine:
    """
    Rank candidates for a role given requirements and a location.

    Scoring factors:
        - Department match (weight 0.3)
        - Position-title keyword overlap (weight 0.3)
        - Location proximity (weight 0.2)
        - Tenure / experience proxy (weight 0.2)

    Example query: “Recommend backend devs for a FinTech project in Chennai.”
    """

    _WEIGHT_DEPT = 0.3
    _WEIGHT_TITLE_OVERLAP = 0.3
    _WEIGHT_LOCATION = 0.2
    _WEIGHT_TENURE = 0.2

    def __init__(
        self,
        employee_service,         # :class:`EmployeeService`
        history_service,          # :class:`EmployeeHistoryService`
        logger: Logger,
    ) -> None:
        # Type hints are duck-typed to avoid circular imports.
        self._employees = employee_service
        self._history = history_service
        self._logger = logger

    def recommend(
        self,
        *,
        role: str = "",
        department: str | None = None,
        location: str | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> List[Dict[str, Any]]:
        """
        Return scored candidates ordered by overall score.

        Returns:
            List of dicts:
            {
              'employee_no', 'full_name', 'department', 'position_title',
              'location', 'tenure_days', 'score', 'explanation'
            }
        """
        start = time.perf_counter()
        op = "recommendation_engine.recommend"

        try:
            role_lower = role.lower()
            loc_lower = (location or "").lower()
            dept_lower = (department or "").lower()

            # Build candidate pool: active employees.
            pool = self._employees.list_all_employees()
            scored: List[Dict[str, Any]] = []

            for emp in pool:
                # Get enriched data via full profile + timeline.
                profile = self._employees.get_full_profile(emp.employee_no)
                dept = (profile.department or "").lower() if profile else ""
                pos = (profile.position_title or "").lower() if profile else ""
                loc = (
                    (profile.city or profile.work_location or "").lower()
                    if profile else ""
                )
                timeline = self._history.build_timeline(emp.employee_no)
                tenure = timeline.stats.total_tenure_days

                # Factor 1: department match.
                dept_match = (
                    _keyword_overlap(dept, dept_lower)
                    if dept_lower else 0.5
                )

                # Factor 2: title keyword overlap.
                title_match = (
                    _keyword_overlap(pos, role_lower)
                    if role_lower else 0.3
                )

                # Factor 3: location.
                loc_match = (
                    1.0 if loc_lower and loc_lower in loc else
                    (0.5 if loc else 0.0)
                ) if loc_lower else 0.5

                # Factor 4: tenure (normalised to [0, 1]: longer is
                # better but caps at 10 years ~ 3650 days).
                tenure_score = min(tenure / 3650.0, 1.0)

                overall = (
                    dept_match * self._WEIGHT_DEPT
                    + title_match * self._WEIGHT_TITLE_OVERLAP
                    + loc_match * self._WEIGHT_LOCATION
                    + tenure_score * self._WEIGHT_TENURE
                )

                reasons = [
                    ExplanationReason(
                        factor="Department match",
                        is_met=dept_match > 0,
                        weight=self._WEIGHT_DEPT,
                        detail=(
                            f"Department '{profile.department}'"
                            f"{' matches' if dept_match > 0 else ' does not match'}."
                            if profile and profile.department
                            else "No department on file."
                        ),
                    ),
                    ExplanationReason(
                        factor="Title overlap",
                        is_met=title_match > 0,
                        weight=self._WEIGHT_TITLE_OVERLAP,
                        detail=(
                            f"Position '{profile.position_title}' vs role '{role}' "
                            f"overlap = {title_match:.2f}."
                            if profile and profile.position_title
                            else "No position title on file."
                        ),
                    ),
                    ExplanationReason(
                        factor="Location",
                        is_met=loc_match >= 0.5,
                        weight=self._WEIGHT_LOCATION,
                        detail=(
                            f"Works from {profile.city or profile.work_location or 'unknown'}."
                            if profile
                            else "No location data."
                        ),
                    ),
                    ExplanationReason(
                        factor="Tenure / experience",
                        is_met=tenure_score > 0,
                        weight=self._WEIGHT_TENURE,
                        detail=(
                            f"{tenure:.0f} days ({tenure / 365:.1f} years) tenure."
                        ),
                    ),
                ]

                explanation = Explanation(
                    score=round(overall, 4),
                    reasons=reasons,
                    summary=(
                        f"{emp.full_name} scored {overall:.2f} for "
                        f"'{role or 'general'}'"
                        + (f" in {department}" if department else "")
                        + (f" at {location}" if location else "")
                        + "."
                    ),
                )

                scored.append({
                    "employee_no": emp.employee_no,
                    "full_name": emp.full_name,
                    "department": profile.department if profile else None,
                    "position_title": profile.position_title if profile else None,
                    "location": profile.city or profile.work_location if profile else None,
                    "tenure_days": tenure,
                    "score": overall,
                    "explanation": explanation,
                })

            scored.sort(key=lambda d: d["score"], reverse=True)
            result = scored[:max_results]

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | role=%s candidates=%d top=%d | %.1fms | OK",
                op, role, len(pool), len(result), duration_ms,
            )
            return result

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR: %s", op, duration_ms, exc,
            )
            raise ServiceError(
                "Recommendation engine failed.",
            ) from exc


# =====================================================================
# 2. Team Builder
# =====================================================================


_PREDEFINED_ROLES = [
    "Team Lead",
    "Backend Developer",
    "Frontend Developer",
    "ML Engineer",
    "Data Engineer",
    "Data Scientist",
    "DevOps Engineer",
    "QA Engineer",
    "Product Manager",
    "Security Engineer",
]


class TeamBuilder:
    """
    Assemble a multi-role team from a project brief.

    For each requested role slot, the agent runs the
    :class:`RecommendationEngine` and picks the top-scored candidate.
    The output is a per-slot result with an :class:`Explanation`.
    """

    def __init__(
        self,
        recommender: RecommendationEngine,
        logger: Logger,
    ) -> None:
        self._rec = recommender
        self._logger = logger

    def build(
        self,
        project_brief: str,
        *,
        roles: List[str] | None = None,
        location: str | None = None,
    ) -> Dict[str, Any]:
        """
        Return a team assembly with one recommended person per slot.

        Args:
            project_brief: Free-text description (e.g. “AI healthcare project”).
            roles: Explicit list of role titles; defaults to the
                full predefined set.
            location: Preferred work location.

        Returns:
            Dict:
            {
              'brief': str,
              'slots': [
                { 'role', 'candidate': {...}, 'score', 'explanation' },
                ...
              ],
              'unfilled': [...],
              'summary': str,
            }
        """
        start = time.perf_counter()
        op = "team_builder.build"

        try:
            slot_roles = roles or _PREDEFINED_ROLES
            slots: List[Dict[str, Any]] = []
            unfilled: List[str] = []

            for role in slot_roles:
                candidates = self._rec.recommend(
                    role=role,
                    location=location,
                    max_results=1,
                )
                if candidates:
                    top = candidates[0]
                    slots.append({
                        "role": role,
                        "candidate": top,
                        "score": top["score"],
                        "explanation": top["explanation"],
                    })
                else:
                    unfilled.append(role)

            summary_parts = [
                f"Team for '{project_brief[:80]}'"
                + (f" in {location}" if location else "")
                + ":",
            ]
            for s in slots:
                c = s["candidate"]
                summary_parts.append(
                    f"  {s['role']} → {c['full_name']} "
                    f"({c.get('department','?')}) score={s['score']:.2f}"
                )
            if unfilled:
                summary_parts.append(
                    f"  Unfilled: {', '.join(unfilled)}"
                )

            result = {
                "brief": project_brief,
                "slots": slots,
                "unfilled": unfilled,
                "summary": "\n".join(summary_parts),
            }

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | roles=%d filled=%d unfilled=%d | %.1fms | OK",
                op, len(slot_roles), len(slots), len(unfilled),
                duration_ms,
            )
            return result

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR: %s", op, duration_ms, exc,
            )
            raise ServiceError("Team builder failed.") from exc


# =====================================================================
# 3. Promotion Analyzer
# =====================================================================


class PromotionAnalyzer:
    """
    Rank employees who are due for promotion using history data.

    Scoring factors:
        - Time since last promotion (longer → higher urgency) (weight 0.4)
        - Total tenure (longer → due) (weight 0.2)
        - Promotions count (fewer → due) (weight 0.2)
        - Stalled flag (weight 0.2)
    """

    _W_TSLP = 0.4
    _W_TENURE = 0.2
    _W_PROMO_COUNT = 0.2
    _W_STALLED = 0.2

    def __init__(
        self,
        history_service,      # :class:`EmployeeHistoryService`
        employee_service,     # :class:`EmployeeService`
        logger: Logger,
    ) -> None:
        self._history = history_service
        self._employees = employee_service
        self._logger = logger

    def analyze(
        self,
        *,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> List[Dict[str, Any]]:
        """
        Return ranked promotion candidates with scored explanations.
        """
        start = time.perf_counter()
        op = "promotion_analyzer.analyze"

        try:
            pool = self._employees.list_all_employees()
            scored: List[Dict[str, Any]] = []

            for emp in pool:
                timeline = self._history.build_timeline(emp.employee_no)
                s = timeline.stats

                tslp = (
                    s.time_since_last_promotion_days
                    if s.time_since_last_promotion_days is not None
                    else s.total_tenure_days
                )
                # Normalise: stall threshold = 4yr = 1460 days.
                tslp_score = min(tslp / 1460.0, 1.0)
                tenure_score = min(s.total_tenure_days / 3650.0, 1.0)
                promo_penalty = (
                    1.0 - min(s.promotions_count / 5.0, 1.0)
                )
                stalled_score = 1.0 if s.is_stalled else 0.0

                overall = (
                    tslp_score * self._W_TSLP
                    + tenure_score * self._W_TENURE
                    + promo_penalty * self._W_PROMO_COUNT
                    + stalled_score * self._W_STALLED
                )

                reasons = [
                    ExplanationReason(
                        factor="Time since last promotion",
                        is_met=tslp > 365 * 2,
                        weight=self._W_TSLP,
                        detail=(
                            f"{tslp:.0f} days "
                            f"({tslp / 365:.1f} years)"
                            if s.time_since_last_promotion_days
                            else "Never promoted — entire tenure "
                            f"({s.total_tenure_days:.0f} days) counted."
                        ),
                    ),
                    ExplanationReason(
                        factor="Tenure",
                        is_met=s.total_tenure_days > 365 * 2,
                        weight=self._W_TENURE,
                        detail=(
                            f"{s.total_tenure_days:.0f} days "
                            f"({s.total_tenure_days / 365:.1f} years)."
                        ),
                    ),
                    ExplanationReason(
                        factor="Prior promotions count",
                        is_met=s.promotions_count <= 2,
                        weight=self._W_PROMO_COUNT,
                        detail=(
                            f"{s.promotions_count} promotion(s) on record."
                        ),
                    ),
                    ExplanationReason(
                        factor="Stalled",
                        is_met=s.is_stalled,
                        weight=self._W_STALLED,
                        detail=(
                            "Currently stalled (no promotion in 4+ years)."
                            if s.is_stalled
                            else "Not stalled."
                        ),
                    ),
                ]

                scored.append({
                    "employee_no": emp.employee_no,
                    "full_name": emp.full_name,
                    "score": round(overall, 4),
                    "explanation": Explanation(
                        score=round(overall, 4),
                        reasons=reasons,
                        summary=(
                            f"{emp.full_name}: promotion urgency "
                            f"{overall:.2f}"
                            + (
                                " (STALLED)" if s.is_stalled else ""
                            )
                            + "."
                        ),
                    ),
                    "stalled": s.is_stalled,
                    "time_since_last_promotion_days": (
                        s.time_since_last_promotion_days
                    ),
                    "promotions_count": s.promotions_count,
                })

            scored.sort(key=lambda d: d["score"], reverse=True)
            result = scored[:max_results]

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | scored=%d top=%d | %.1fms | OK",
                op, len(scored), len(result), duration_ms,
            )
            return result

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR", op, duration_ms,
            )
            raise ServiceError("Promotion analyzer failed.") from exc


# =====================================================================
# 4. Transfer Analyzer
# =====================================================================


class TransferAnalyzer:
    """
    Analyse workforce distribution and suggest internal moves.

    Seeks employees who have spent their entire tenure in one
    department and matches them to growing / understaffed
    departments from the analytics snapshot.
    """

    def __init__(
        self,
        employee_service,
        history_service,
        analytics_agent,    # :class:`AnalyticsAgent`
        logger: Logger,
    ) -> None:
        self._employees = employee_service
        self._history = history_service
        self._analytics = analytics_agent
        self._logger = logger

    def analyze(
        self,
        *,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> List[Dict[str, Any]]:
        """
        Return employees with their current dept and a suggested
        destination dept, plus scored reasons.
        """
        start = time.perf_counter()
        op = "transfer_analyzer.analyze"

        try:
            pool = self._employees.list_all_employees()
            snapshot = self._analytics.full_snapshot()
            growing_depts = {
                d["department"] for d in
                snapshot.get("by_department", [])
                if d.get("count", 0) > 0
            }

            transfers: List[Dict[str, Any]] = []

            for emp in pool:
                profile = self._employees.get_full_profile(emp.employee_no)
                current = profile.department if profile else None
                timeline = self._history.build_timeline(emp.employee_no)
                transfer_events = [
                    e for e in timeline.events
                    if e.event_type == HistoryEventType.TRANSFERRED
                ]
                # Candidate: at least 1 year tenure in one dept and
                # zero or very few transfers.
                if not current or timeline.stats.total_tenure_days < 365:
                    continue
                if len(transfer_events) > 2:
                    continue

                # Find a destination dept different from current.
                candidates = sorted(growing_depts - {current}) if current else []
                if not candidates:
                    continue

                dest = candidates[0]
                tenure_years = timeline.stats.total_tenure_days / 365
                reason_is_loyal = (
                    len(transfer_events) <= 1
                    and timeline.stats.total_tenure_days > 365 * 2
                )

                reasons = [
                    ExplanationReason(
                        factor="Low internal mobility",
                        is_met=len(transfer_events) <= 1,
                        weight=0.4,
                        detail=(
                            f"{len(transfer_events)} previous transfer(s)."
                        ),
                    ),
                    ExplanationReason(
                        factor="Tenure stability",
                        is_met=tenure_years > 2,
                        weight=0.3,
                        detail=(
                            f"{tenure_years:.1f} years in current dept."
                        ),
                    ),
                    ExplanationReason(
                        factor="Destination has headroom",
                        is_met=True,
                        weight=0.3,
                        detail=(
                            f"{dest} is a growing / active department."
                        ),
                    ),
                ]
                score = 0.5 + (
                    0.5 if reason_is_loyal else 0.2
                )
                explanation = Explanation(
                    score=round(score, 4),
                    reasons=reasons,
                    summary=(
                        f"{emp.full_name} ({current}) → "
                        f"{dest}: loyal, stable candidate for "
                        f"internal mobility."
                    ),
                )

                transfers.append({
                    "employee_no": emp.employee_no,
                    "full_name": emp.full_name,
                    "from_department": current,
                    "to_department": dest,
                    "score": score,
                    "explanation": explanation,
                })

            transfers.sort(key=lambda d: d["score"], reverse=True)
            result = transfers[:max_results]

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | candidates=%d top=%d | %.1fms | OK",
                op, len(transfers), len(result), duration_ms,
            )
            return result

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR", op, duration_ms,
            )
            raise ServiceError("Transfer analyzer failed.") from exc


# =====================================================================
# 5. Attrition Risk
# =====================================================================


class AttritionRisk:
    """
    Flag indicators of attrition risk:

        - Long tenure without promotion (stalled).
        - Stagnant role (same dept > X years, same title > X years).
        - Department that itself is growing a lot (churn risk).
        - Tenure among the longest in the workforce.

    Returns scored, explainable risk assessments.
    """

    _W_STALLED = 0.4
    _W_STAGNANT_ROLE = 0.3
    _W_DEPT_CHURN = 0.15
    _W_LONG_TENURE = 0.15

    def __init__(
        self,
        history_service,
        employee_service,
        analytics_agent,
        logger: Logger,
    ) -> None:
        self._history = history_service
        self._employees = employee_service
        self._analytics = analytics_agent
        self._logger = logger

    def analyze(
        self,
        *,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> List[Dict[str, Any]]:
        """
        Return employees with attrition risk score, explanation,
        and the identified indicators.
        """
        start = time.perf_counter()
        op = "attrition_risk.analyze"

        try:
            pool = self._employees.list_all_employees()
            snapshot = self._analytics.full_snapshot()
            all_tenures = [
                self._history.build_timeline(
                    e.employee_no,
                ).stats.total_tenure_days
                for e in pool
            ]
            p90_tenure = (
                _p90(all_tenures) if all_tenures else 0.0
            )
            growing_depts = {
                d["department"]
                for d in snapshot.get("fastest_growing_department", [])
                if d.get("hires", 0) > 0
            }

            risks: List[Dict[str, Any]] = []

            for emp in pool:
                timeline = self._history.build_timeline(emp.employee_no)
                s = timeline.stats
                profile = self._employees.get_full_profile(emp.employee_no)
                dept = profile.department if profile else None

                stalled = s.is_stalled
                tslp = (
                    s.time_since_last_promotion_days
                    if s.time_since_last_promotion_days is not None
                    else s.total_tenure_days
                )

                # Stagnant role: same dept for > 5yr, no position change.
                dept_tenure = (
                    s.time_in_each_role.get(
                        profile.position_title or "",
                        0.0,
                    )
                    if profile and profile.position_title
                    else 0.0
                )
                stagnant = (
                    dept_tenure > 365 * 5
                    and s.total_tenure_days > 365 * 3
                    and s.promotions_count == 0
                )

                # Long tenure in the top 10 %.
                long_tenure = (
                    p90_tenure > 0
                    and s.total_tenure_days >= p90_tenure
                )

                # Dept churn risk.
                dept_churn = (
                    dept is not None
                    and dept in growing_depts
                )

                stalled_score = 1.0 if stalled else 0.0
                stagnant_score = 1.0 if stagnant else 0.0
                dept_churn_score = 1.0 if dept_churn else 0.0
                long_tenure_score = 1.0 if long_tenure else 0.0

                overall = (
                    stalled_score * self._W_STALLED
                    + stagnant_score * self._W_STAGNANT_ROLE
                    + dept_churn_score * self._W_DEPT_CHURN
                    + long_tenure_score * self._W_LONG_TENURE
                )

                reasons = [
                    ExplanationReason(
                        factor="Career stalled",
                        is_met=stalled,
                        weight=self._W_STALLED,
                        detail=(
                            f"No promotion in {tslp:.0f} days."
                            if stalled
                            else "Not stalled."
                        ),
                    ),
                    ExplanationReason(
                        factor="Stagnant role",
                        is_met=stagnant,
                        weight=self._W_STAGNANT_ROLE,
                        detail=(
                            f"Same role for {dept_tenure:.0f} days, "
                            f"no promotions."
                            if stagnant
                            else "Not stagnant."
                        ),
                    ),
                    ExplanationReason(
                        factor="Department churn",
                        is_met=dept_churn,
                        weight=self._W_DEPT_CHURN,
                        detail=(
                            f"Department '{dept}' is growing fast."
                            if dept_churn
                            else f"Dept '{dept}' is not a high-churn zone."
                            if dept
                            else "No department data."
                        ),
                    ),
                    ExplanationReason(
                        factor="Long tenure (top 10%)",
                        is_met=long_tenure,
                        weight=self._W_LONG_TENURE,
                        detail=(
                            f"Tenure {s.total_tenure_days:.0f} days "
                            f"(≥ p90 = {p90_tenure:.0f} days)."
                        ),
                    ),
                ]

                explanation = Explanation(
                    score=round(overall, 4),
                    reasons=reasons,
                    summary=(
                        f"{emp.full_name}: attrition risk {overall:.2f}"
                        + (" (HIGH)" if overall > 0.4 else " (low)")
                        + "."
                    ),
                )

                risks.append({
                    "employee_no": emp.employee_no,
                    "full_name": emp.full_name,
                    "score": overall,
                    "explanation": explanation,
                    "indicators": {
                        "stalled": stalled,
                        "stagnant_role": stagnant,
                        "dept_churn": dept_churn,
                        "long_tenure": long_tenure,
                    },
                })

            risks.sort(key=lambda d: d["score"], reverse=True)
            result = risks[:max_results]

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | scored=%d top=%d high_risk=%d | %.1fms | OK",
                op, len(risks), len(result),
                sum(1 for r in result if r["score"] > 0.4),
                duration_ms,
            )
            return result

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR", op, duration_ms,
            )
            raise ServiceError("Attrition risk analysis failed.") from exc


# =====================================================================
# 6. Skill-Gap Analysis + Hiring-Cost Estimation
# =====================================================================


class SkillGapAgent:
    """
    For a target (e.g. “new AI centre in Hyderabad”) identify
    missing skills vs required and estimate hiring cost.

    ** IMPORTANT ASSUMPTION **: salary data does NOT exist in the
    current schema. Cost estimates use a fixed placeholder
    (\"PLACEHOLDER\" per hire). Every consumer MUST state this
    clearly in the output.
    """

    PLACEHOLDER_COST = 60_000

    def __init__(
        self,
        employee_service,
        analytics_agent,
        logger: Logger,
    ) -> None:
        self._employees = employee_service
        self._analytics = analytics_agent
        self._logger = logger

    def analyze(
        self,
        target_description: str,
        *,
        required_roles: List[str] | None = None,
        location: str | None = None,
        growth_pct: float | None = None,
    ) -> Dict[str, Any]:
        """
        Analyse the gap between the current workforce and the
        target.

        Args:
            target_description: e.g. “New AI centre in Hyderabad” or
                “Grow the AI division by 40%”.
            required_roles: Explicit role list; if omitted we infer
                from the target keywords.
            location: Target location.
            growth_pct: Percentage growth target (e.g. 40.0).

        Returns:
            Dict with gap_roles, current_count, needed, estimated_cost,
            explanation, and assumption note.
        """
        start = time.perf_counter()
        op = "skill_gap.analyze"

        try:
            roles = required_roles or _infer_roles(target_description)
            snapshot = self._analytics.full_snapshot()
            dept_data = snapshot.get("by_department", [])

            # Map each department that roughly matches the target
            # theme to its current headcount.
            full_pool = self._employees.list_all_employees()
            headcount = len([e for e in full_pool if e.is_active])

            if growth_pct:
                target_count = int(headcount * (1 + growth_pct / 100))
                needed = max(target_count - headcount, 0)
            else:
                # Estimate: count employees matching any role keyword
                # and compare against a simple role-baseline.
                loc_match = 0
                for emp in full_pool:
                    profile = self._employees.get_full_profile(emp.employee_no)
                    loc = (profile.city or profile.work_location or "").lower()
                    if location and loc and location.lower() in loc:
                        loc_match += 1
                needed = max(len(roles) - (loc_match or 1), 0)

            total_cost = needed * self.PLACEHOLDER_COST

            reasons = [
                ExplanationReason(
                    factor="Required roles",
                    is_met=True,
                    weight=0.4,
                    detail=(
                        f"Target roles: {', '.join(roles[:5])}"
                        + (f" +{len(roles)-5} more" if len(roles) > 5 else "")
                        + "."
                    ),
                ),
                ExplanationReason(
                    factor="Current headcount",
                    is_met=headcount > 0,
                    weight=0.2,
                    detail=f"Current workforce: {headcount} active employees.",
                ),
                ExplanationReason(
                    factor="Estimated to hire",
                    is_met=needed > 0,
                    weight=0.4,
                    detail=(
                        f"Approximately {needed} new hires needed. "
                        f"Estimated cost: ${total_cost:,.0f} "
                        f"({self.PLACEHOLDER_COST:,.0f} placeholder "
                        f"per hire — NO salary data exists)."
                    ),
                ),
            ]

            explanation = Explanation(
                score=min(0.5 + needed / max(headcount, 1) * 0.5, 1.0),
                reasons=reasons,
                summary=(
                    f"For '{target_description}': "
                    + (
                        f"grow from {headcount} to {target_count} "
                        f"(need {needed} hires, ~${total_cost:,.0f})."
                        if growth_pct
                        else (
                            f"estimated {needed} hires needed at "
                            f" ${total_cost:,.0f} placeholder cost."
                        )
                    )
                    + " COST IS A PLACEHOLDER — no salary data exists."
                ),
            )

            result = {
                "target": target_description,
                "required_roles": roles,
                "current_headcount": headcount,
                "estimated_hires": needed,
                "estimated_cost": total_cost,
                "cost_assumption": (
                    "PLACEHOLDER cost per hire — salary data does "
                    "NOT exist in the current schema."
                ),
                "explanation": explanation,
            }

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | roles=%d needed=%d cost=$%.0f | %.1fms | OK",
                op, len(roles), needed, total_cost, duration_ms,
            )
            return result

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR", op, duration_ms,
            )
            raise ServiceError("Skill-gap analysis failed.") from exc


# =====================================================================
# 7. Insight Agent (history-backed workforce scorecard)
# =====================================================================


class InsightAgent:
    """
    History-backed workforce scorecard that answers time-based
    executive questions:

        - Fastest growing department (from real hire history).
        - Largest engineering hub (by employee location).
        - Understaffed departments.
        - Hiring forecast.

    Every metric is returned with an :class:`Explanation`.
    """

    def __init__(
        self,
        analytics_agent,     # :class:`AnalyticsAgent`
        logger: Logger,
    ) -> None:
        self._analytics = analytics_agent
        self._logger = logger

    def full_scorecard(self) -> Dict[str, Any]:
        """
        Return a structured workforce scorecard with scored
        explanations for every metric.
        """
        start = time.perf_counter()
        op = "insight_agent.full_scorecard"

        try:
            data = self._analytics.full_snapshot()
            # Also get the insight additions.
            # Insight data belongs to the repository.  Some analytics-agent
            # implementations do not expose this optional method.
            insight_provider = getattr(self._analytics, "_repo", None)
            if insight_provider is not None and hasattr(
                insight_provider, "insight_snapshot"
            ):
                insight = insight_provider.insight_snapshot()
            else:
                insight_method = getattr(self._analytics, "insight_snapshot", None)
                insight = insight_method() if callable(insight_method) else {}
            if not isinstance(insight, dict):
                insight = {}

            headcount = insight.get("total_headcount", data.get("total_headcount", 0))

            # Fastest growing department.
            fastest = insight.get("fastest_growing_department", [])
            fastest_expl = Explanation(
                score=1.0 if fastest else 0.0,
                reasons=[
                    ExplanationReason(
                        factor="Fastest growing department",
                        is_met=len(fastest) > 0,
                        weight=1.0,
                        detail=(
                            f"Top: {fastest[0]['department']} "
                            f"with {fastest[0]['hires']} hires "
                            f"in the last 12 months."
                            if fastest
                            else "No recent hire data."
                        ),
                    ),
                ],
            )

            # Largest hub.
            hub = insight.get("largest_engineering_hub", [])
            hub_expl = Explanation(
                score=1.0 if hub else 0.0,
                reasons=[
                    ExplanationReason(
                        factor="Largest hub",
                        is_met=len(hub) > 0,
                        weight=1.0,
                        detail=(
                            f"{hub[0]['city']}: {hub[0]['count']} "
                            f"employees."
                            if hub
                            else "No location data."
                        ),
                    ),
                ],
            )

            # Understaffed.
            under = insight.get("understaffed_departments", [])
            under_expl = Explanation(
                score=1.0 if under else 0.5,
                reasons=[
                    ExplanationReason(
                        factor="Understaffed departments",
                        is_met=len(under) > 0,
                        weight=1.0,
                        detail=(
                            f"{len(under)} departments below 10% "
                            f"of {headcount} total."
                            if under
                            else "No understaffed departments."
                        ),
                    ),
                ],
            )

            # Hiring forecast.
            fc = insight.get("hiring_forecast", {})
            fc_expl = Explanation(
                score=(
                    1.0
                    if fc.get("avg_hires_per_year", 0) > 0
                    else 0.0
                ),
                reasons=[
                    ExplanationReason(
                        factor="Hiring forecast",
                        is_met=fc.get("projected_next_year_hires", 0) > 0,
                        weight=1.0,
                        detail=(
                            f"Projected {fc.get('projected_next_year_hires', 0):.0f} "
                            f"hires next year "
                            f"({fc.get('note', '')})."
                        ),
                    ),
                ],
            )

            result = {
                "total_headcount": headcount,
                "avg_tenure_years": insight.get(
                    "average_tenure_years",
                    data.get("average_tenure_years", 0),
                ),
                "fastest_growing": {
                    "data": fastest,
                    "explanation": fastest_expl,
                },
                "largest_hub": {
                    "data": hub,
                    "explanation": hub_expl,
                },
                "understaffed": {
                    "data": under,
                    "explanation": under_expl,
                },
                "hiring_forecast": {
                    "data": fc,
                    "explanation": fc_expl,
                },
            }

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | %.1fms | OK", op, duration_ms,
            )
            return result

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR", op, duration_ms,
            )
            raise ServiceError("Insight scorecard failed.") from exc


# =====================================================================
# Module-level helpers
# =====================================================================


def _keyword_overlap(field_text: str, query_text: str) -> float:
    """
    Measure the fraction of query tokens that appear in the field
    text. Returns a number in ``[0, 1]``.
    """
    if not query_text:
        return 0.5  # Neutral when no query.
    query_tokens = set(query_text.replace(",", " ").split())
    field_tokens = set(field_text.replace(",", " ").split())
    if not query_tokens:
        return 0.0
    common = query_tokens & field_tokens
    return len(common) / len(query_tokens)


def _p90(values: List[float]) -> float:
    """
    90-th percentile of a list of floats. Returns 0 for empty list.
    """
    if not values:
        return 0.0
    items = sorted(values)
    idx = int(len(items) * 0.9)
    return items[min(idx, len(items) - 1)]


_INFER_ROLES_MAP: Dict[str, List[str]] = {
    "ai": ["ML Engineer", "Data Scientist", "Data Engineer"],
    "healthcare": ["Data Engineer", "QA Engineer", "Security Engineer"],
    "fintech": ["Backend Developer", "Data Engineer", "Security Engineer"],
    "devops": ["DevOps Engineer", "Backend Developer"],
    "research": ["ML Engineer", "Data Scientist", "Team Lead"],
    "engineering": ["Backend Developer", "Frontend Developer", "QA Engineer"],
}


def _infer_roles(target: str) -> List[str]:
    """
    Heuristically infer role list from target-description keywords.
    Falls back to a generic set.
    """
    lower = target.lower()
    roles: List[str] = []
    for keyword, rlist in _INFER_ROLES_MAP.items():
        if keyword in lower:
            roles.extend(rlist)
    if not roles:
        roles = [
            "Backend Developer",
            "Data Engineer",
            "QA Engineer",
            "Team Lead",
        ]
    return list(dict.fromkeys(roles))  # dedup, preserve order
