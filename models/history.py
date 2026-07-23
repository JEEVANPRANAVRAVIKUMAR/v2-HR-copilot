"""
Employee history (audit-trail) models.

`EmployeeHistory` is one row in the event log; `EmployeeTimeline` is
the chronological view for a single employee plus computed career
stats. `Explanation` is the shared scored-reasons structure used by
recommendations and semantic search.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List

from pydantic import Field

from models.common import BaseSchema


# =====================================================================
# Event log row
# =====================================================================


class HistoryEventType(str, Enum):
    """Every event kind that can land in ``employee_history``."""

    HIRED = "hired"
    PROMOTED = "promoted"
    TRANSFERRED = "transferred"
    DEPARTMENT_CHANGED = "department_changed"
    POSITION_CHANGED = "position_changed"
    STATUS_CHANGED = "status_changed"
    SALARY_CHANGED = "salary_changed"
    CREATED = "created"
    UPDATED = "updated"
    REACTIVATED = "reactivated"
    DEACTIVATED = "deactivated"
    DELETED = "deleted"


class EmployeeHistory(BaseSchema):
    """A single audit-trail row."""

    id: int | None = None
    employee_id: int
    employee_no: str
    event_type: HistoryEventType
    from_value: str | None = None
    to_value: str | None = None
    field: str | None = None
    note: str | None = None
    occurred_at: datetime | None = None


class EmployeeHistoryCreate(BaseSchema):
    """Payload used to insert a history row."""

    employee_id: int
    employee_no: str
    event_type: HistoryEventType
    from_value: str | None = None
    to_value: str | None = None
    field: str | None = None
    note: str | None = None


# =====================================================================
# Timeline + computed career stats
# =====================================================================


class CareerStats(BaseSchema):
    """
    Computed career statistics for one employee.

    All durations are expressed in **days** as floats so callers can
    format them in any unit they like.
    """

    total_tenure_days: float = 0.0
    """Time from earliest recorded event (typically ``hired``) until now."""

    time_in_each_role: dict[str, float] = Field(default_factory=dict)
    """Role/position_title -> days spent in that role."""

    promotions_count: int = 0
    """How many ``promoted`` events exist in the timeline."""

    time_since_last_promotion_days: float | None = None
    """``None`` if the employee has never been promoted."""

    average_time_between_promotions_days: float | None = None
    """``None`` if fewer than two promotions are recorded."""

    is_stalled: bool = False
    """True when ``time_since_last_promotion_days`` exceeds the threshold."""

    stall_threshold_days: float = 0.0
    """Threshold used to decide ``is_stalled``."""


class TimelineEntry(BaseSchema):
    """
    One human-readable entry in an employee's timeline.

    Combines a raw `EmployeeHistory` row with convenient display
    fields computed by the aggregator.
    """

    event_type: HistoryEventType
    occurred_at: datetime
    from_value: str | None = None
    to_value: str | None = None
    field: str | None = None
    note: str | None = None
    description: str = ""
    """Pre-formatted one-liner, e.g. 'Promoted from Engineer to Senior Engineer'."""


class EmployeeTimeline(BaseSchema):
    """Full history view for a single employee."""

    employee_no: str
    full_name: str | None = None
    events: List[TimelineEntry] = Field(default_factory=list)
    stats: CareerStats = Field(default_factory=CareerStats)
    narration: str | None = None
    """Optional LLM-written plain-English summary."""

# =====================================================================
# Shared Explanation model (Scope 3)
# =====================================================================


class ExplanationReason(BaseSchema):
    """
    One itemized reason contributing to an overall score.

    Used by recommendations and semantic search to explain WHY a
    particular candidate/result was chosen.
    """

    factor: str
    """What dimension this reason refers to (e.g. 'Skill match', 'Tenure')."""

    is_met: bool
    """Whether this factor was satisfied for this candidate."""

    weight: float = 1.0
    """Relative importance of this factor in the overall score (0..1)."""

    detail: str | None = None
    """Optional human-readable explanation, e.g. '5 of 7 required skills matched'."""


class Explanation(BaseSchema):
    """
    Shared explanation structure.

    Any scored recommendation or search result can carry one of
    these so the UI/LLM can answer "why did you recommend X?" with
    itemized, weighted reasons rather than a black-box score.
    """

    score: float = 0.0
    """Overall confidence/similarity score (0..1)."""

    reasons: List[ExplanationReason] = Field(default_factory=list)
    """Itemized reasons contributing to ``score``."""

    summary: str | None = None
    """Optional short human-readable summary of the explanation."""
