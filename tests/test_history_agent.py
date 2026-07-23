"""
Tests for the HistoryAgent.

Covers:
  - LLM narration of a per-employee timeline.
  - Stall query narration.
  - Name/number resolution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from logging import Logger
from unittest.mock import create_autospec, MagicMock

import pytest

from ai import GroqLLM, HistoryAgent
from database.queries import EmployeeHistoryRepository
from models.employee import Employee
from models.history import (
    CareerStats,
    EmployeeTimeline,
    HistoryEventType,
    TimelineEntry,
)
from services import EmployeeHistoryService, EmployeeService
from utils.exceptions import ServiceError

from .conftest import make_employee_row


@pytest.fixture
def llm():
    return create_autospec(GroqLLM, instance=True)


@pytest.fixture
def history_service():
    return create_autospec(EmployeeHistoryService, instance=True)


@pytest.fixture
def employee_service():
    return create_autospec(EmployeeService, instance=True)


@pytest.fixture
def logger():
    return create_autospec(Logger, instance=True)


@pytest.fixture
def agent(llm, history_service, employee_service, logger):
    return HistoryAgent(
        llm=llm,
        history_service=history_service,
        employee_service=employee_service,
        logger=logger,
        default_stall_threshold_years=4.0,
    )


def _make_employee(**overrides) -> Employee:
    row = make_employee_row(**overrides)
    return Employee.model_validate(row)


def _timeline(**overrides) -> EmployeeTimeline:
    defaults = dict(
        employee_no="EMP001",
        full_name="Rahul",
        events=[
            TimelineEntry(
                event_type=HistoryEventType.HIRED,
                occurred_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
                to_value="Engineer",
                description="Hired",
            ),
        ],
        stats=CareerStats(
            total_tenure_days=365 * 5,
            time_in_each_role={"Engineer": 365 * 5},
            promotions_count=0,
            time_since_last_promotion_days=None,
            average_time_between_promotions_days=None,
            is_stalled=False,
            stall_threshold_days=365 * 4,
        ),
    )
    defaults.update(overrides)
    return EmployeeTimeline(**defaults)


# ====================================================================
# answer — stall queries
# ====================================================================


class TestStallQueries:
    def test_stall_question_without_name_triggers_stall_path(
        self, agent, employee_service, history_service, llm,
    ):
        # No employees stalled → the agent returns a canned message
        # without calling the LLM.
        employee_service.list_all_employees.return_value = []
        result = agent.answer("Whose career has stalled for 4+ years?")
        assert "No employees" in result
        llm.generate.assert_not_called()

    def test_stall_query_with_stalled_employees_narrates_them(
        self, agent, employee_service, history_service, llm,
    ):
        emp1 = _make_employee(employee_no="EMP001", full_name="Alice")
        emp2 = _make_employee(employee_no="EMP002", full_name="Bob")
        employee_service.list_all_employees.return_value = [emp1, emp2]
        # history_service.build_timeline returns a stalled timeline.
        history_service.build_timeline.return_value = _timeline(
            is_stalled_in_stats=True,
            promotions_count=1,
            time_since_last_promotion_days=365 * 6,  # well over 4 years
        )
        llm.generate.return_value = "Alice and Bob are stalled."

        result = agent.answer("Who has stalled in their career?")
        # LLM was called once for narration.
        assert llm.generate.call_count == 1
        assert result == "Alice and Bob are stalled."


# ====================================================================
# answer — per-employee timeline narration
# ====================================================================


class TestPerEmployeeNarration:
    def test_resolves_by_employee_number(self, agent, employee_service, history_service, llm):
        emp = _make_employee(employee_no="EMP005", full_name="Rahul")
        employee_service.get_employee_by_no.return_value = emp
        history_service.build_timeline.return_value = _timeline(employee_no="EMP005", full_name="Rahul")
        llm.generate.return_value = "Rahul has 5 years tenure."

        result = agent.answer("Show me EMP005's history")
        employee_service.get_employee_by_no.assert_called_once_with("EMP005")
        assert result == "Rahul has 5 years tenure."

    def test_resolves_by_name(self, agent, employee_service, history_service, llm):
        emp = _make_employee(employee_no="EMP005", full_name="Rahul")
        employee_service.search_employees.return_value = [emp]
        history_service.build_timeline.return_value = _timeline(employee_no="EMP005", full_name="Rahul")
        llm.generate.return_value = "Rahul's timeline narrated."

        result = agent.answer("Show me Rahul's history")
        employee_service.search_employees.assert_called()
        assert "Rahul" in result

    def test_no_employee_found_returns_friendly_message(self, agent, employee_service, llm):
        employee_service.get_employee_by_no.return_value = None
        employee_service.search_employees.return_value = []
        llm.generate.return_value = "should not be called"

        result = agent.answer("Show me Zzz Nonexistent's history")
        assert "couldn't find" in result.lower()
        llm.generate.assert_not_called()

    def test_unexpected_failure_wraps_in_service_error(
        self, agent, employee_service, llm,
    ):
        employee_service.get_employee_by_no.side_effect = Exception("DB down")
        with pytest.raises(ServiceError):
            agent.answer("Show me EMP005's history")


# ====================================================================
# build_timeline (structured, no LLM)
# ====================================================================


class TestBuildTimeline:
    def test_returns_timeline_from_service(self, agent, history_service):
        timeline = _timeline(employee_no="EMP010", full_name="Anya")
        history_service.build_timeline.return_value = timeline
        result = agent.build_timeline("EMP010", stall_threshold_years=5)
        assert result.employee_no == "EMP010"
        assert result.full_name == "Anya"
        # The threshold passed is converted from years to days.
        _kwargs = history_service.build_timeline.call_args.kwargs
        assert _kwargs["stall_threshold_days"] == pytest.approx(365 * 5)


# ====================================================================
# find_stalled_employees (no LLM)
# ====================================================================


class TestFindStalledEmployees:
    def test_returns_only_stalled_sorted_by_time_since_last_promo_desc(
        self, agent, employee_service, history_service,
    ):
        alice = _make_employee(employee_no="EMP001", full_name="Alice")
        bob = _make_employee(employee_no="EMP002", full_name="Bob")
        carol = _make_employee(employee_no="EMP003", full_name="Carol")
        employee_service.list_all_employees.return_value = [alice, bob, carol]

        # Use side_effects to return different timelines per employee.
        stalled_long = _timeline()
        stalled_long.stats.time_since_last_promotion_days = 365 * 10
        stalled_long.stats.is_stalled = True
        stalled_short = _timeline()
        stalled_short.stats.time_since_last_promotion_days = 365 * 5
        stalled_short.stats.is_stalled = True
        not_stalled = _timeline()
        not_stalled.stats.time_since_last_promotion_days = 365 * 1
        not_stalled.stats.is_stalled = False

        history_service.build_timeline.side_effect = [
            stalled_long,   # Alice
            stalled_short,  # Bob
            not_stalled,    # Carol
        ]
        result = agent.find_stalled_employees(threshold_years=4)
        # Carol filtered out, Alice (10yr) first, then Bob (5yr).
        assert len(result) == 2
        assert result[0]["employee_no"] == "EMP001"  # Alice
        assert result[1]["employee_no"] == "EMP002"  # Bob

    def test_no_stalled_returns_empty_list(self, agent, employee_service, history_service):
        emp = _make_employee()
        employee_service.list_all_employees.return_value = [emp]
        timeline = _timeline()
        timeline.stats.is_stalled = False
        history_service.build_timeline.return_value = timeline
        assert agent.find_stalled_employees() == []


def _timeline(**overrides):
    """Local helper: build a Timeline with is_stalled flipped by override."""
    base = _make_base_timeline()
    if overrides.pop("is_stalled_in_stats", False):
        base.stats.is_stalled = True
    for k, v in overrides.items():
        if hasattr(base.stats, k):
            setattr(base.stats, k, v)
        elif hasattr(base, k):
            setattr(base, k, v)
    return base


def _make_base_timeline() -> EmployeeTimeline:
    return EmployeeTimeline(
        employee_no="EMP001",
        full_name="X",
        events=[
            TimelineEntry(
                event_type=HistoryEventType.HIRED,
                occurred_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
                description="Hired",
            )
        ],
        stats=CareerStats(
            total_tenure_days=365 * 5,
            time_in_each_role={"Engineer": 365 * 5},
            promotions_count=0,
            time_since_last_promotion_days=None,
            average_time_between_promotions_days=None,
            is_stalled=False,
            stall_threshold_days=365 * 4,
        ),
    )
