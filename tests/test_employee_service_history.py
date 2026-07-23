"""
Tests confirming that every EmployeeService write path auto-logs
to the audit trail via EmployeeHistoryService.

Each test asserts:
  - The primary write succeeds (returns the expected Employee).
  - The history service was called with the right event type(s).
"""

from __future__ import annotations

from logging import Logger
from unittest.mock import create_autospec

import pytest

from database.queries import EmployeeHistoryRepository, EmployeeRepository
from models.employee import Employee, EmployeeCreate, EmployeeUpdate
from models.history import HistoryEventType
from services import EmployeeHistoryService, EmployeeService
from utils.exceptions import EmployeeNotFoundError

from .conftest import make_employee_row


@pytest.fixture
def repo():
    return create_autospec(EmployeeRepository, instance=True)


@pytest.fixture
def history_repo():
    return create_autospec(EmployeeHistoryRepository, instance=True)


@pytest.fixture
def logger():
    return create_autospec(Logger, instance=True)


@pytest.fixture
def history_service(history_repo, logger):
    return EmployeeHistoryService(history_repo, logger)


@pytest.fixture
def service_with_history(repo, history_service, logger):
    return EmployeeService(
        repository=repo,
        logger=logger,
        history_service=history_service,
    )


@pytest.fixture
def service_without_history(repo, logger):
    return EmployeeService(repository=repo, logger=logger)


def _emp(**overrides):
    return Employee.model_validate(make_employee_row(**overrides))


# ====================================================================
# Backward compatibility — no history service
# ====================================================================


class TestNoHistoryService:
    def test_create_still_works_without_history(self, service_without_history, repo):
        repo.exists.return_value = False
        repo.create.return_value = _emp()
        result = service_without_history.create_employee(
            EmployeeCreate(employee_no="EMP001", full_name="John"),
        )
        assert result.employee_no == "EMP001"


# ====================================================================
# create
# ====================================================================


class TestCreateAutoLogs:
    def test_logs_created_and_hired_events(
        self, service_with_history, repo, history_service,
    ):
        repo.exists.return_value = False
        repo.create.return_value = _emp()
        # Spy on the history service's log_event by replacing it.
        events: list = []
        original = history_service.log_event
        def spy(*args, **kwargs):
            events.append(kwargs.get("event_type"))
            return original(*args, **kwargs)
        history_service.log_event = spy

        service_with_history.create_employee(
            EmployeeCreate(employee_no="EMP001", full_name="John"),
        )

        assert HistoryEventType.CREATED in events
        assert HistoryEventType.HIRED in events


# ====================================================================
# update
# ====================================================================


class TestUpdateAutoLogs:
    def test_logs_status_changed_for_is_active_field(
        self, service_with_history, repo, history_service,
    ):
        before = _emp(is_active=True)
        after = _emp(is_active=False)
        repo.get_by_employee_no.return_value = before
        repo.update.return_value = after

        events: list = []
        original = history_service.log_event
        def spy(*args, **kwargs):
            events.append((kwargs.get("event_type"), kwargs.get("field")))
            return original(*args, **kwargs)
        history_service.log_event = spy

        service_with_history.update_employee(
            "EMP001", EmployeeUpdate(is_active=False),
        )
        # We expect a status_changed event on is_active.
        statuses = [t for (t, f) in events if f == "is_active"]
        assert HistoryEventType.STATUS_CHANGED in statuses

    def test_logs_updated_for_full_name_field(
        self, service_with_history, repo, history_service,
    ):
        before = _emp(full_name="John")
        after = _emp(full_name="Jonathan")
        repo.get_by_employee_no.return_value = before
        repo.update.return_value = after

        events: list = []
        original = history_service.log_event
        def spy(*args, **kwargs):
            events.append((kwargs.get("event_type"), kwargs.get("field")))
            return original(*args, **kwargs)
        history_service.log_event = spy

        service_with_history.update_employee(
            "EMP001", EmployeeUpdate(full_name="Jonathan"),
        )
        # Generic 'updated' event for non-status fields.
        assert (HistoryEventType.UPDATED, "full_name") in events

    def test_no_event_when_value_unchanged(
        self, service_with_history, repo, history_service,
    ):
        before = _emp(full_name="John")
        after = _emp(full_name="John")
        repo.get_by_employee_no.return_value = before
        repo.update.return_value = after

        events: list = []
        original = history_service.log_event
        def spy(*args, **kwargs):
            events.append(kwargs.get("event_type"))
            return original(*args, **kwargs)
        history_service.log_event = spy

        service_with_history.update_employee(
            "EMP001", EmployeeUpdate(full_name="John"),
        )
        # No changes → no audit rows.
        assert events == []


# ====================================================================
# activate / deactivate / delete
# ====================================================================


class TestStatusTransitionsAutoLog:
    def test_activate_logs_reactivated_and_status_changed(
        self, service_with_history, repo, history_service,
    ):
        before = _emp(is_active=False)
        after = _emp(is_active=True)
        repo.get_by_employee_no.return_value = before
        repo.activate.return_value = after

        events: list = []
        original = history_service.log_event
        def spy(*args, **kwargs):
            events.append(kwargs.get("event_type"))
            return original(*args, **kwargs)
        history_service.log_event = spy

        service_with_history.activate_employee("EMP001")
        assert HistoryEventType.REACTIVATED in events
        assert HistoryEventType.STATUS_CHANGED in events

    def test_deactivate_logs_deactivated_and_status_changed(
        self, service_with_history, repo, history_service,
    ):
        before = _emp(is_active=True)
        after = _emp(is_active=False)
        repo.get_by_employee_no.return_value = before
        repo.deactivate.return_value = after

        events: list = []
        original = history_service.log_event
        def spy(*args, **kwargs):
            events.append(kwargs.get("event_type"))
            return original(*args, **kwargs)
        history_service.log_event = spy

        service_with_history.deactivate_employee("EMP001")
        assert HistoryEventType.DEACTIVATED in events
        assert HistoryEventType.STATUS_CHANGED in events

    def test_delete_logs_deleted_and_status_changed(
        self, service_with_history, repo, history_service,
    ):
        before = _emp(is_active=True)
        after = _emp(is_active=False)
        repo.get_by_employee_no.return_value = before
        repo.delete.return_value = after

        events: list = []
        original = history_service.log_event
        def spy(*args, **kwargs):
            events.append(kwargs.get("event_type"))
            return original(*args, **kwargs)
        history_service.log_event = spy

        service_with_history.delete_employee("EMP001")
        assert HistoryEventType.DELETED in events
        assert HistoryEventType.STATUS_CHANGED in events


# ====================================================================
# Promotion / Transfer helper paths
# ====================================================================


class TestPromotionAndTransfer:
    def test_record_promotion_logs_promoted_event(
        self, service_with_history, repo, history_service,
    ):
        repo.get_by_employee_no.return_value = _emp()

        events: list = []
        original = history_service.log_event
        def spy(*args, **kwargs):
            events.append((kwargs.get("event_type"), kwargs.get("from_value"), kwargs.get("to_value")))
            return original(*args, **kwargs)
        history_service.log_event = spy

        service_with_history.record_promotion(
            "EMP001", from_role="Engineer", to_role="Senior Engineer",
        )
        assert (HistoryEventType.PROMOTED, "Engineer", "Senior Engineer") in events

    def test_record_transfer_logs_transferred_event(
        self, service_with_history, repo, history_service,
    ):
        repo.get_by_employee_no.return_value = _emp()

        events: list = []
        original = history_service.log_event
        def spy(*args, **kwargs):
            events.append((kwargs.get("event_type"), kwargs.get("from_value"), kwargs.get("to_value")))
            return original(*args, **kwargs)
        history_service.log_event = spy

        service_with_history.record_transfer(
            "EMP001", from_department="Sales", to_department="Engineering",
        )
        assert (HistoryEventType.TRANSFERRED, "Sales", "Engineering") in events


# ====================================================================
# Audit failure isolation
# ====================================================================


class TestAuditFailureIsolation:
    def test_primary_create_succeeds_even_if_audit_fails(
        self, service_with_history, repo, history_service,
    ):
        repo.exists.return_value = False
        repo.create.return_value = _emp()
        # Make the history service explode.
        history_service.log_event = lambda *a, **k: (_ for _ in ()).throw(
            Exception("Audit DB down"),
        )
        # Must NOT raise.
        result = service_with_history.create_employee(
            EmployeeCreate(employee_no="EMP001", full_name="John"),
        )
        assert result.employee_no == "EMP001"
