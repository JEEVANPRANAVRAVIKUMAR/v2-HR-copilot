"""
Employee history repository.

Performs all database operations against the ``employee_history``
audit-trail table. Repositories do not interpret events — they just
read and write rows. All interpretation happens in the history
service and the history agent.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from core.constants import EMPLOYEES_TABLE, EMPLOYEE_HISTORY_TABLE
from database.queries.base_repository import BaseRepository
from models.history import EmployeeHistory, EmployeeHistoryCreate
from utils.exceptions import RepositoryError


class EmployeeHistoryRepository(BaseRepository):
    """
    Read/write access to the employee audit trail.
    """

    def insert(self, event: EmployeeHistoryCreate) -> EmployeeHistory:
        """
        Insert one history event.

        Args:
            event: Payload describing the event.

        Returns:
            The persisted row as an :class:`EmployeeHistory`.

        Raises:
            RepositoryError: On any write failure.
        """
        try:
            payload = event.model_dump()
            payload.setdefault("occurred_at", datetime.utcnow().isoformat())

            response = self._execute(
                self.client
                .table(EMPLOYEE_HISTORY_TABLE)
                .insert(payload)
            )
            if not self._has_data(response):
                raise RepositoryError("History insert returned no rows.")

            self.logger.info(
                "History event recorded: emp=%s type=%s",
                event.employee_no,
                event.event_type.value,
            )
            return EmployeeHistory.model_validate(response.data[0])

        except RepositoryError:
            raise
        except Exception as exc:
            self.logger.exception("Failed inserting history event.")
            raise RepositoryError("Unable to record history event.") from exc

    def insert_many(
        self, events: List[EmployeeHistoryCreate],
    ) -> List[EmployeeHistory]:
        """
        Insert multiple events in a single round-trip.

        Args:
            events: List of payloads.

        Returns:
            The persisted rows.
        """
        if not events:
            return []
        try:
            payload = []
            now = datetime.utcnow().isoformat()
            for e in events:
                row = e.model_dump()
                row.setdefault("occurred_at", now)
                payload.append(row)

            response = self._execute(
                self.client
                .table(EMPLOYEE_HISTORY_TABLE)
                .insert(payload)
            )
            if not self._has_data(response):
                raise RepositoryError("Bulk history insert returned no rows.")
            return [
                EmployeeHistory.model_validate(row)
                for row in response.data
            ]
        except RepositoryError:
            raise
        except Exception as exc:
            self.logger.exception("Failed bulk inserting history events.")
            raise RepositoryError(
                "Unable to bulk record history events.",
            ) from exc

    def get_by_employee_no(
        self,
        employee_no: str,
        *,
        limit: int | None = None,
    ) -> List[EmployeeHistory]:
        """
        Return all events for an employee, newest-first by default.

        Args:
            employee_no: Employee identifier.
            limit: Cap on number of rows.

        Returns:
            List of history rows ordered by ``occurred_at`` descending.
        """
        try:
            q = (
                self.client
                .table(EMPLOYEE_HISTORY_TABLE)
                .select("*")
                .eq("employee_no", employee_no)
                .order("occurred_at", desc=True)
            )
            if limit:
                q = q.limit(limit)

            response = self._execute(q)
            if not self._has_data(response):
                return []
            return [
                EmployeeHistory.model_validate(row)
                for row in response.data
            ]
        except Exception as exc:
            self.logger.exception(
                "Failed fetching history for %s.", employee_no,
            )
            raise RepositoryError("Unable to fetch history.") from exc

    def get_by_employee_id(
        self,
        employee_id: int,
        *,
        limit: int | None = None,
    ) -> List[EmployeeHistory]:
        """
        Return all events for an employee by internal id.
        """
        try:
            q = (
                self.client
                .table(EMPLOYEE_HISTORY_TABLE)
                .select("*")
                .eq("employee_id", employee_id)
                .order("occurred_at", desc=True)
            )
            if limit:
                q = q.limit(limit)
            response = self._execute(q)
            if not self._has_data(response):
                return []
            return [
                EmployeeHistory.model_validate(row)
                for row in response.data
            ]
        except Exception as exc:
            self.logger.exception(
                "Failed fetching history for id=%s.", employee_id,
            )
            raise RepositoryError("Unable to fetch history.") from exc

    def get_events_by_type(
        self,
        event_type: str,
        *,
        limit: int | None = None,
    ) -> List[EmployeeHistory]:
        """
        Return all events of a given type, most recent first.

        Used for stall-detection queries such as "show me everyone
        whose last ``promoted`` event was more than N days ago".
        """
        try:
            q = (
                self.client
                .table(EMPLOYEE_HISTORY_TABLE)
                .select("*")
                .eq("event_type", event_type)
                .order("occurred_at", desc=True)
            )
            if limit:
                q = q.limit(limit)
            response = self._execute(q)
            if not self._has_data(response):
                return []
            return [
                EmployeeHistory.model_validate(row)
                for row in response.data
            ]
        except Exception as exc:
            self.logger.exception(
                "Failed fetching events of type %s.", event_type,
            )
            raise RepositoryError("Unable to fetch events.") from exc

    def get_latest_promotion(
        self, employee_no: str,
    ) -> EmployeeHistory | None:
        """
        Return the most recent ``promoted`` event for an employee,
        or ``None`` if they have never been promoted.
        """
        try:
            response = self._execute(
                self.client
                .table(EMPLOYEE_HISTORY_TABLE)
                .select("*")
                .eq("employee_no", employee_no)
                .eq("event_type", "promoted")
                .order("occurred_at", desc=True)
                .limit(1)
            )
            if not self._has_data(response):
                return None
            return EmployeeHistory.model_validate(response.data[0])
        except Exception as exc:
            self.logger.exception(
                "Failed fetching latest promotion for %s.", employee_no,
            )
            raise RepositoryError(
                "Unable to fetch latest promotion.",
            ) from exc


__all__ = ["EmployeeHistoryRepository"]
