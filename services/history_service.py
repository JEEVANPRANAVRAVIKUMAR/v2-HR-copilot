"""
Employee history service.

This service is the *only* place outside the repository that writes
to the audit trail. It exposes a high-level ``log_event`` API used
by the EmployeeService to record every significant write, and a
``build_timeline`` API that aggregates raw rows into a
human-readable timeline plus computed career stats.

The service does NOT call the LLM — that lives in the
``HistoryAgent``.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from logging import Logger
from typing import List

from database.queries import EmployeeHistoryRepository
from models.history import (
    CareerStats,
    EmployeeHistory,
    EmployeeHistoryCreate,
    EmployeeTimeline,
    HistoryEventType,
    TimelineEntry,
)
from utils.exceptions import HistoryError, ServiceError


# Event types that count as a "promotion" for stall detection.
PROMOTION_EVENTS = frozenset({
    HistoryEventType.PROMOTED.value,
})


class EmployeeHistoryService:
    """
    Auto-logger + timeline aggregator for the employee audit trail.

    Used by ``EmployeeService`` to record every write, and by the
    ``HistoryAgent`` to surface career timelines and stats.
    """

    def __init__(
        self,
        repository: EmployeeHistoryRepository,
        logger: Logger,
    ) -> None:
        self._repo = repository
        self._logger = logger

    # ----------------------------------------------------------------
    # Auto-logging (called by EmployeeService write paths)
    # ----------------------------------------------------------------

    def log_event(
        self,
        employee_id: int,
        employee_no: str,
        event_type: HistoryEventType,
        *,
        from_value: str | None = None,
        to_value: str | None = None,
        field: str | None = None,
        note: str | None = None,
    ) -> EmployeeHistory:
        """
        Record one audit-trail event.

        Failures here are logged but are NOT propagated to the caller:
        the brief mandates that every write records an event, but we
        also must not break a successful employee write because the
        audit table was unavailable. Callers that want strict
        behaviour should check ``occurred_at`` is not ``None``.

        Args:
            employee_id: Internal DB id of the employee.
            employee_no: Employee identifier.
            event_type: Type of event.
            from_value: Optional prior value of the changed field.
            to_value: Optional new value.
            field: Optional name of the changed field.
            note: Optional human-readable note.

        Returns:
            The persisted history row. On failure, a row with
            ``id=None`` and ``occurred_at=None`` is returned.
        """
        start = time.perf_counter()
        op = "history_service.log_event"

        try:
            event = EmployeeHistoryCreate(
                employee_id=employee_id,
                employee_no=employee_no,
                event_type=event_type,
                from_value=from_value,
                to_value=to_value,
                field=field,
                note=note,
            )
            row = self._repo.insert(event)

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | emp=%s type=%s | %.1fms | OK",
                op, employee_no, event_type.value, duration_ms,
            )
            return row

        except Exception as exc:
            # Never raise from the logger path; the primary write
            # already succeeded. We log loudly instead.
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | emp=%s type=%s | %.1fms | FAILED: %s",
                op, employee_no, event_type.value, duration_ms, exc,
            )
            return EmployeeHistory(
                id=None,
                employee_id=employee_id,
                employee_no=employee_no,
                event_type=event_type,
                from_value=from_value,
                to_value=to_value,
                field=field,
                note=note,
                occurred_at=None,
            )

    # ----------------------------------------------------------------
    # Read/aggregation
    # ----------------------------------------------------------------

    def get_history(
        self,
        employee_no: str,
        *,
        limit: int | None = None,
    ) -> List[EmployeeHistory]:
        """
        Return raw audit rows for an employee, newest-first.
        """
        start = time.perf_counter()
        op = "history_service.get_history"
        try:
            rows = self._repo.get_by_employee_no(
                employee_no, limit=limit,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | emp=%s | rows=%d | %.1fms | OK",
                op, employee_no, len(rows), duration_ms,
            )
            return rows
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | emp=%s | %.1fms | ERROR", op, employee_no, duration_ms,
            )
            raise ServiceError("Failed to retrieve history.") from exc

    def build_timeline(
        self,
        employee_no: str,
        full_name: str | None = None,
        *,
        stall_threshold_days: float = 365.0 * 4,
        now: datetime | None = None,
    ) -> EmployeeTimeline:
        """
        Build a chronological timeline plus computed career stats for
        an employee.

        Args:
            employee_no: Employee identifier.
            full_name: Optional display name to attach.
            stall_threshold_days: Days without a promotion that
                counts as "stalled". Defaults to 4 years.
            now: Reference timestamp (defaults to UTC now); injectable
                for deterministic tests.

        Returns:
            :class:`EmployeeTimeline` with events in chronological
            order (oldest first) and computed :class:`CareerStats`.
        """
        start = time.perf_counter()
        op = "history_service.build_timeline"

        try:
            rows = self._repo.get_by_employee_no(employee_no)
            # Newest first from repo; flip to chronological order:
            chronological = list(reversed(rows))

            now_dt = now or datetime.now(timezone.utc)

            # Retrieve joining date fallback
            profile = None
            joining_dt = None
            try:
                from database.queries import EmployeeRepository
                emp_repo = EmployeeRepository()
                profile = emp_repo.get_full_profile(employee_no)
                if profile and profile.joining_date:
                    joining_dt = datetime(
                        profile.joining_date.year,
                        profile.joining_date.month,
                        profile.joining_date.day,
                        tzinfo=timezone.utc
                    )
            except Exception:
                pass

            entries = [
                self._row_to_entry(r) for r in chronological
            ]
            stats = self._compute_stats(
                chronological, now_dt, stall_threshold_days,
                joining_dt=joining_dt, profile=profile,
            )

            timeline = EmployeeTimeline(
                employee_no=employee_no,
                full_name=full_name,
                events=entries,
                stats=stats,
            )

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | emp=%s | events=%d | stalled=%s | %.1fms | OK",
                op, employee_no, len(entries), stats.is_stalled,
                duration_ms,
            )
            return timeline

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | emp=%s | %.1fms | ERROR",
                op, employee_no, duration_ms,
            )
            raise HistoryError("Failed to build timeline.") from exc

    # ----------------------------------------------------------------
    # Internal: stats
    # ----------------------------------------------------------------

    def _compute_stats(
        self,
        rows: List[EmployeeHistory],
        now: datetime,
        stall_threshold_days: float,
        joining_dt: datetime | None = None,
        profile: Any = None,
    ) -> CareerStats:
        """
        Compute tenure, role durations, promotion counts, and
        stall detection from a chronological list of audit rows.
        """
        # Determine the earliest date (hire/origin).
        earliest_dt = joining_dt
        if earliest_dt is None and rows:
            earliest = rows[0].occurred_at
            if earliest is not None:
                earliest_dt = self._as_datetime(earliest)
                if earliest_dt.tzinfo is None:
                    earliest_dt = earliest_dt.replace(tzinfo=timezone.utc)

        if earliest_dt is None:
            return CareerStats(stall_threshold_days=stall_threshold_days)

        total_tenure_days = (now - earliest_dt).total_seconds() / 86400.0

        # Time in each role: walk events; the role is "the most
        # recent position_changed/promoted event by the time of the
        # next event". Use a default of "Unknown" until first role
        # event.
        role_changes = [
            r for r in rows
            if r.event_type in (
                HistoryEventType.POSITION_CHANGED,
                HistoryEventType.PROMOTED,
                HistoryEventType.HIRED,
            )
            and r.occurred_at is not None
        ]

        time_in_each_role: dict[str, float] = {}
        if role_changes:
            # Sort by occurred_at (already sorted chronologically)
            for i, rc in enumerate(role_changes):
                role = (
                    rc.to_value
                    or rc.note
                    or "Unknown"
                )
                start_dt = self._as_datetime(rc.occurred_at)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                end_dt = (
                    self._as_datetime(role_changes[i + 1].occurred_at)
                    if i + 1 < len(role_changes)
                    else now
                )
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                duration = (end_dt - start_dt).total_seconds() / 86400.0
                if duration < 0:
                    duration = 0.0
                time_in_each_role[role] = (
                    time_in_each_role.get(role, 0.0) + duration
                )
        elif joining_dt and profile and profile.position_title:
            # Assume their entire tenure is in their current role
            role = profile.position_title
            duration = (now - joining_dt).total_seconds() / 86400.0
            if duration < 0:
                duration = 0.0
            time_in_each_role[role] = duration

        # Promotions
        promotion_rows = [
            r for r in rows
            if r.event_type == HistoryEventType.PROMOTED
            and r.occurred_at is not None
        ]
        promotions_count = len(promotion_rows)

        # Time since last promotion
        time_since_last_promotion_days: float | None = None
        if promotion_rows:
            last = self._as_datetime(promotion_rows[-1].occurred_at)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            time_since_last_promotion_days = (
                now - last
            ).total_seconds() / 86400.0

        # Average time between promotions
        average_time_between_promotions_days: float | None = None
        if promotions_count >= 2:
            first = self._as_datetime(promotion_rows[0].occurred_at)
            last = self._as_datetime(promotion_rows[-1].occurred_at)
            if first.tzinfo is None:
                first = first.replace(tzinfo=timezone.utc)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            span_days = (last - first).total_seconds() / 86400.0
            average_time_between_promotions_days = max(
                span_days / (promotions_count - 1), 0.0,
            )

        # Stall detection: stalled if we've gone longer than the
        # threshold since our last promotion (and we have at least
        # one promotion).
        is_stalled = (
            time_since_last_promotion_days is not None
            and time_since_last_promotion_days >= stall_threshold_days
        )

        return CareerStats(
            total_tenure_days=round(total_tenure_days, 2),
            time_in_each_role=time_in_each_role,
            promotions_count=promotions_count,
            time_since_last_promotion_days=(
                round(time_since_last_promotion_days, 2)
                if time_since_last_promotion_days is not None
                else None
            ),
            average_time_between_promotions_days=(
                round(average_time_between_promotions_days, 2)
                if average_time_between_promotions_days is not None
                else None
            ),
            is_stalled=is_stalled,
            stall_threshold_days=stall_threshold_days,
        )

    # ----------------------------------------------------------------
    # Internal: row -> timeline entry
    # ----------------------------------------------------------------

    @staticmethod
    def _row_to_entry(row: EmployeeHistory) -> TimelineEntry:
        """
        Render an audit row as a human-readable timeline entry.
        """
        description = EmployeeHistoryService._describe(row)
        return TimelineEntry(
            event_type=row.event_type,
            occurred_at=row.occurred_at or datetime.now(timezone.utc),
            from_value=row.from_value,
            to_value=row.to_value,
            field=row.field,
            note=row.note,
            description=description,
        )

    @staticmethod
    def _describe(row: EmployeeHistory) -> str:
        """
        Build a one-liner description for an event.
        """
        ts = (
            row.occurred_at.strftime("%Y-%m-%d")
            if row.occurred_at else "?"
        )
        prefix = f"[{ts}] "
        t = row.event_type

        if t == HistoryEventType.CREATED:
            return f"{prefix}Employee record created."
        if t == HistoryEventType.HIRED:
            return f"{prefix}Hired." + (
                f" (start: {row.to_value})" if row.to_value else ""
            )
        if t == HistoryEventType.PROMOTED:
            return (
                f"{prefix}Promoted"
                + (f" from {row.from_value}" if row.from_value else "")
                + (f" to {row.to_value}." if row.to_value else ".")
            )
        if t == HistoryEventType.TRANSFERRED:
            return (
                f"{prefix}Transferred"
                + (f" from {row.from_value}" if row.from_value else "")
                + (f" to {row.to_value}." if row.to_value else ".")
            )
        if t == HistoryEventType.DEPARTMENT_CHANGED:
            return (
                f"{prefix}Department changed"
                + (f" from {row.from_value}" if row.from_value else "")
                + (f" to {row.to_value}." if row.to_value else ".")
            )
        if t == HistoryEventType.POSITION_CHANGED:
            return (
                f"{prefix}Position changed"
                + (f" from {row.from_value}" if row.from_value else "")
                + (f" to {row.to_value}." if row.to_value else ".")
            )
        if t == HistoryEventType.STATUS_CHANGED:
            return (
                f"{prefix}Status changed"
                + (f" from {row.from_value}" if row.from_value else "")
                + (f" to {row.to_value}." if row.to_value else ".")
            )
        if t == HistoryEventType.SALARY_CHANGED:
            return (
                f"{prefix}Salary changed"
                + (f" from {row.from_value}" if row.from_value else "")
                + (f" to {row.to_value}." if row.to_value else ".")
            )
        if t == HistoryEventType.REACTIVATED:
            return f"{prefix}Reactivated."
        if t == HistoryEventType.DEACTIVATED:
            return f"{prefix}Deactivated."
        if t == HistoryEventType.DELETED:
            return f"{prefix}Soft-deleted."
        if t == HistoryEventType.UPDATED:
            return f"{prefix}Updated: {row.field or 'record'} changed." + (
                f" {row.from_value} -> {row.to_value}."
                if row.from_value or row.to_value
                else ""
            )
        return f"{prefix}{t.value}."

    # ----------------------------------------------------------------
    # Internal: datetime coercion
    # ----------------------------------------------------------------

    @staticmethod
    def _as_datetime(value) -> datetime:
        """
        Coerce a value into a :class:`datetime`. Strings are parsed
        via ``datetime.fromisoformat`` (with ``Z`` stripped).
        """
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            cleaned = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(cleaned)
            except ValueError:
                # Fallback: try without tz
                return datetime.fromisoformat(value.split("+")[0])
        # Shouldn't happen with the validated schema, but be defensive.
        return datetime.now(timezone.utc)
