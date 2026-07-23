"""
Employee service.

Encapsulates all employee-related business logic. Services must NOT
run raw queries — every database operation is delegated to the
appropriate repository.

Every write method (create / update / activate / deactivate /
delete) records an event in the audit trail via the optional
:class:`EmployeeHistoryService`. If no history service is wired
(as in legacy test fixtures), the write still succeeds.
"""

from __future__ import annotations

import time
from logging import Logger
from typing import Iterable, List

from database.queries import EmployeeRepository
from models.employee import Employee, EmployeeCreate, EmployeeUpdate
from models.history import HistoryEventType
from models.responses import EmployeeProfileResponse
from utils.exceptions import (
    DuplicateEmployeeError,
    EmployeeNotFoundError,
    ServiceError,
    ValidationError,
)


class EmployeeService:
    """
    Business-logic layer for employee operations.

    Responsibilities:
        - Validate input using Pydantic schemas.
        - Enforce business rules (unique employee_no, status transitions).
        - Coordinate between repositories.
        - Log every operation with timing and status.
        - Record an audit-trail event for every write.
    """

    def __init__(
        self,
        repository: EmployeeRepository,
        logger: Logger,
        history_service: object | None = None,
    ) -> None:
        """
        Args:
            repository: The employee repository.
            logger: Logger.
            history_service: Optional :class:`EmployeeHistoryService`.
                When provided, every write path records an audit
                event. When omitted (or ``None``), writes proceed
                without history logging — kept for backward compat
                with legacy tests and minimal-deployment scenarios.
        """
        self._repo = repository
        self._logger = logger
        # Stored as Any to avoid a circular import with
        # services.history_service. The duck-typed surface we use
        # is `log_event(employee_id, employee_no, event_type, ...)`.
        self._history_service = history_service

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    def _log_operation(
        self,
        operation: str,
        employee_no: str | None,
        duration_ms: float,
        status: str,
        detail: str | None = None,
    ) -> None:
        extra = detail or ""
        self._logger.info(
            "%s | emp=%s | %.1fms | %s %s",
            operation,
            employee_no or "-",
            duration_ms,
            status,
            extra,
        )

    def _record_event(
        self,
        employee: Employee,
        event_type: HistoryEventType,
        *,
        from_value: str | None = None,
        to_value: str | None = None,
        field: str | None = None,
        note: str | None = None,
    ) -> None:
        """
        Record an audit event if the history service is wired.

        Failures here are intentionally swallowed — the primary write
        has already succeeded and we must not roll it back. The
        :class:`EmployeeHistoryService` itself logs loudly.
        """
        if self._history_service is None:
            return
        if employee.id is None:
            # Should not happen for created/updated employees, but
            # be defensive — skip rather than raise.
            self._logger.warning(
                "Cannot record history event: employee.id is None "
                "(emp_no=%s, event=%s).",
                employee.employee_no, event_type.value,
            )
            return
        try:
            self._history_service.log_event(
                employee_id=employee.id,
                employee_no=employee.employee_no,
                event_type=event_type,
                from_value=from_value,
                to_value=to_value,
                field=field,
                note=note,
            )
        except Exception as exc:
            # Never raise from the audit-log path.
            self._logger.exception(
                "History logging failed for emp=%s event=%s: %s",
                employee.employee_no, event_type.value, exc,
            )

    def _record_field_changes(
        self,
        before: Employee,
        after: Employee,
        updated_fields: Iterable[str],
        base_event_type: HistoryEventType = HistoryEventType.UPDATED,
    ) -> None:
        """
        Walk updated field names and record one history event per
        actually-changed field. For ``is_active`` we emit a
        specific ``status_changed`` event; for everything else we
        use the generic ``updated`` event type.
        """
        for field_name in updated_fields:
            old_v = getattr(before, field_name, None)
            new_v = getattr(after, field_name, None)
            if old_v == new_v:
                continue
            event_type = (
                HistoryEventType.STATUS_CHANGED
                if field_name == "is_active"
                else base_event_type
            )
            self._record_event(
                after,
                event_type,
                from_value=(
                    str(old_v) if old_v is not None else None
                ),
                to_value=(
                    str(new_v) if new_v is not None else None
                ),
                field=field_name,
            )

    # ----------------------------------------------------------------
    # Create
    # ----------------------------------------------------------------

    def create_employee(self, data: EmployeeCreate) -> Employee:
        """
        Create a new employee after validating business rules.

        Records a ``created`` event (and a ``hired`` event by
        convention) on success.

        Rules enforced:
            - employee_no must be unique.

        Raises:
            DuplicateEmployeeError: If the employee_no already exists.
            ServiceError: On unexpected failures.
        """
        start = time.perf_counter()
        op = "create_employee"

        try:
            if self._repo.exists(data.employee_no):
                duration_ms = (time.perf_counter() - start) * 1000
                self._log_operation(
                    op, data.employee_no, duration_ms, "FAILED",
                    detail="Duplicate employee_no",
                )
                raise DuplicateEmployeeError(
                    f"Employee '{data.employee_no}' already exists."
                )

            employee = self._repo.create(data)

            # Audit trail — record creation.
            self._record_event(
                employee,
                HistoryEventType.CREATED,
                to_value=employee.employee_no,
                note=f"Employee created: {employee.full_name}",
            )
            # Convention: also emit a `hired` event so the timeline
            # has an "origin" point used for total-tenure computation.
            self._record_event(
                employee,
                HistoryEventType.HIRED,
                to_value=employee.full_name,
                note="Initial hire",
            )

            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(
                op, data.employee_no, duration_ms, "OK",
            )
            return employee

        except (DuplicateEmployeeError, ServiceError):
            raise

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(
                op, data.employee_no, duration_ms, "ERROR",
            )
            raise ServiceError("Failed to create employee.") from exc

    # ----------------------------------------------------------------
    # Read
    # ----------------------------------------------------------------

    def get_employee_by_id(self, employee_id: int) -> Employee | None:
        """
        Retrieve an employee by internal database id.
        """
        start = time.perf_counter()
        op = "get_employee_by_id"

        try:
            employee = self._repo.get_by_id(employee_id)

            duration_ms = (time.perf_counter() - start) * 1000
            status = "OK" if employee else "NOT_FOUND"
            self._log_operation(op, None, duration_ms, status)
            return employee

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, None, duration_ms, "ERROR")
            raise ServiceError("Failed to retrieve employee.") from exc

    def get_employee_by_no(self, employee_no: str) -> Employee | None:
        """
        Retrieve an employee by employee number.
        """
        start = time.perf_counter()
        op = "get_employee_by_no"

        try:
            employee = self._repo.get_by_employee_no(employee_no)

            duration_ms = (time.perf_counter() - start) * 1000
            status = "OK" if employee else "NOT_FOUND"
            self._log_operation(op, employee_no, duration_ms, status)
            return employee

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "ERROR")
            raise ServiceError("Failed to retrieve employee.") from exc

    def search_employees(
        self,
        query: str | None = None,
        is_active: bool | None = None,
        department: str | None = None,
        position_title: str | None = None,
    ) -> List[Employee]:
        """
        Search employees with optional filters.
        """
        start = time.perf_counter()
        op = "search_employees"

        try:
            results = self._repo.search(
                query=query,
                is_active=is_active,
                department=department,
                position_title=position_title,
            )

            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(
                op, None, duration_ms, "OK",
                detail=f"results={len(results)}",
            )
            return results

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, None, duration_ms, "ERROR")
            raise ServiceError("Failed to search employees.") from exc

    def list_all_employees(self) -> List[Employee]:
        """
        Retrieve all employees.
        """
        start = time.perf_counter()
        op = "list_all_employees"

        try:
            employees = self._repo.get_all()

            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(
                op, None, duration_ms, "OK",
                detail=f"total={len(employees)}",
            )
            return employees

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, None, duration_ms, "ERROR")
            raise ServiceError("Failed to list employees.") from exc

    def get_full_profile(
        self,
        employee_no: str,
    ) -> EmployeeProfileResponse | None:
        """
        Retrieve the complete employee profile.
        """
        start = time.perf_counter()
        op = "get_full_profile"

        try:
            profile = self._repo.get_full_profile(employee_no)

            duration_ms = (time.perf_counter() - start) * 1000
            status = "OK" if profile else "NOT_FOUND"
            self._log_operation(op, employee_no, duration_ms, status)
            return profile

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "ERROR")
            raise ServiceError("Failed to retrieve full profile.") from exc

    # ----------------------------------------------------------------
    # Update
    # ----------------------------------------------------------------

    def update_employee(
        self,
        employee_no: str,
        data: EmployeeUpdate,
    ) -> Employee:
        """
        Update employee information.

        For every field that actually changed, a ``status_changed``
        (for ``is_active``) or generic ``updated`` event is recorded.

        Rules enforced:
            - Employee must exist.
            - At least one field must be provided for update.

        Raises:
            EmployeeNotFoundError: If the employee does not exist.
            ValidationError: If no fields are provided.
            ServiceError: On unexpected failures.
        """
        start = time.perf_counter()
        op = "update_employee"

        try:
            updated_fields = list(data.model_dump(exclude_none=True).keys())
            if not updated_fields:
                raise ValidationError(
                    "At least one field must be provided for update."
                )

            existing = self._repo.get_by_employee_no(employee_no)
            if existing is None:
                duration_ms = (time.perf_counter() - start) * 1000
                self._log_operation(
                    op, employee_no, duration_ms, "FAILED",
                    detail="Employee not found",
                )
                raise EmployeeNotFoundError(
                    f"Employee '{employee_no}' not found."
                )

            employee = self._repo.update(employee_no, data)

            # Audit trail — one event per changed field.
            self._record_field_changes(existing, employee, updated_fields)

            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "OK")
            return employee

        except (EmployeeNotFoundError, ValidationError, ServiceError):
            raise

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "ERROR")
            raise ServiceError("Failed to update employee.") from exc

    # ----------------------------------------------------------------
    # Status transitions
    # ----------------------------------------------------------------

    def activate_employee(self, employee_no: str) -> Employee:
        """
        Activate an employee.

        Records a ``reactivated`` event AND a ``status_changed``
        event (from ``"inactive"`` to ``"active"``) on success.

        Raises:
            EmployeeNotFoundError: If the employee does not exist.
        """
        start = time.perf_counter()
        op = "activate_employee"

        try:
            existing = self._repo.get_by_employee_no(employee_no)
            if existing is None:
                raise EmployeeNotFoundError(
                    f"Employee '{employee_no}' not found."
                )

            employee = self._repo.activate(employee_no)

            # Specific event for "reactivated" semantics.
            self._record_event(
                employee,
                HistoryEventType.REACTIVATED,
                from_value=str(existing.is_active),
                to_value="True",
            )
            # Plus the canonical status_changed event so consumers
            # don't need to special-case reactivate vs update.
            self._record_event(
                employee,
                HistoryEventType.STATUS_CHANGED,
                from_value="inactive",
                to_value="active",
                field="is_active",
            )

            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "OK")
            return employee

        except EmployeeNotFoundError:
            raise

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "ERROR")
            raise ServiceError("Failed to activate employee.") from exc

    def deactivate_employee(self, employee_no: str) -> Employee:
        """
        Deactivate an employee.

        Records a ``deactivated`` event AND a ``status_changed``
        event (from ``"active"`` to ``"inactive"``) on success.

        Raises:
            EmployeeNotFoundError: If the employee does not exist.
        """
        start = time.perf_counter()
        op = "deactivate_employee"

        try:
            existing = self._repo.get_by_employee_no(employee_no)
            if existing is None:
                raise EmployeeNotFoundError(
                    f"Employee '{employee_no}' not found."
                )

            employee = self._repo.deactivate(employee_no)

            self._record_event(
                employee,
                HistoryEventType.DEACTIVATED,
                from_value=str(existing.is_active),
                to_value="False",
            )
            self._record_event(
                employee,
                HistoryEventType.STATUS_CHANGED,
                from_value="active",
                to_value="inactive",
                field="is_active",
            )

            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "OK")
            return employee

        except EmployeeNotFoundError:
            raise

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "ERROR")
            raise ServiceError("Failed to deactivate employee.") from exc

    # ----------------------------------------------------------------
    # Delete
    # ----------------------------------------------------------------

    def delete_employee(self, employee_no: str) -> Employee:
        """
        Soft-delete an employee (marks as inactive).

        Equivalent to ``deactivate`` but additionally records a
        ``deleted`` event on success.

        Raises:
            EmployeeNotFoundError: If the employee does not exist.
        """
        start = time.perf_counter()
        op = "delete_employee"

        try:
            existing = self._repo.get_by_employee_no(employee_no)
            if existing is None:
                raise EmployeeNotFoundError(
                    f"Employee '{employee_no}' not found."
                )

            employee = self._repo.delete(employee_no)

            self._record_event(
                employee,
                HistoryEventType.DELETED,
                from_value="active",
                to_value="inactive",
                note="Soft-delete (deactivated)",
            )
            self._record_event(
                employee,
                HistoryEventType.STATUS_CHANGED,
                from_value="active",
                to_value="inactive",
                field="is_active",
            )

            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "OK")
            return employee

        except EmployeeNotFoundError:
            raise

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "ERROR")
            raise ServiceError("Failed to delete employee.") from exc

    # ----------------------------------------------------------------
    # Promotions / Transfers (high-level writes that log to history)
    # ----------------------------------------------------------------

    def record_promotion(
        self,
        employee_no: str,
        *,
        from_role: str | None,
        to_role: str,
        note: str | None = None,
    ) -> Employee:
        """
        Record a promotion for an existing employee.

        This writes a ``promoted`` event into the audit trail and
        updates the employee record (currently only ``full_name`` is
        a mutable field on the Employee table, so the promotion is
        purely an audit-trail event). The companion ``position``
        changes are expected to be reflected in position history
        by callers.

        Raises:
            EmployeeNotFoundError: If the employee does not exist.
        """
        start = time.perf_counter()
        op = "record_promotion"

        try:
            existing = self._repo.get_by_employee_no(employee_no)
            if existing is None:
                raise EmployeeNotFoundError(
                    f"Employee '{employee_no}' not found."
                )

            self._record_event(
                existing,
                HistoryEventType.PROMOTED,
                from_value=from_role,
                to_value=to_role,
                field="position_title",
                note=note,
            )

            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "OK")
            return existing

        except EmployeeNotFoundError:
            raise
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "ERROR")
            raise ServiceError("Failed to record promotion.") from exc

    def record_transfer(
        self,
        employee_no: str,
        *,
        from_department: str | None,
        to_department: str,
        note: str | None = None,
    ) -> Employee:
        """
        Record a department transfer as a ``transferred`` event.

        Raises:
            EmployeeNotFoundError: If the employee does not exist.
        """
        start = time.perf_counter()
        op = "record_transfer"

        try:
            existing = self._repo.get_by_employee_no(employee_no)
            if existing is None:
                raise EmployeeNotFoundError(
                    f"Employee '{employee_no}' not found."
                )

            self._record_event(
                existing,
                HistoryEventType.TRANSFERRED,
                from_value=from_department,
                to_value=to_department,
                field="department",
                note=note,
            )

            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "OK")
            return existing

        except EmployeeNotFoundError:
            raise
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_operation(op, employee_no, duration_ms, "ERROR")
            raise ServiceError("Failed to record transfer.") from exc
