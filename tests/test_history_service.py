"""
Tests for EmployeeHistoryService.timeline/aggregation.

Covers the career-stats computations (total tenure, time in each
role, promotions count, time since last promotion, average between
promotions, stall detection) and the auto-logging ``log_event``
behaviour (must not raise on failure — primary writes must succeed
regardless of audit-trail availability).
"""

from __future__ import annotations

from datetime import datetime, timezone
from logging import Logger
from unittest.mock import create_autospec

import pytest

from database.queries import EmployeeHistoryRepository
from models.history import (
    EmployeeHistory,
    HistoryEventType,
)
from services import EmployeeHistoryService
from utils.exceptions import ServiceError


@pytest.fixture
def repo():
    return create_autospec(EmployeeHistoryRepository, instance=True)


@pytest.fixture
def logger():
    return create_autospec(Logger, instance=True)


@pytest.fixture
def service(repo, logger):
    return EmployeeHistoryService(repository=repo, logger=logger)


def _h(
    *,
    event_type: HistoryEventType,
    occurred_at: str,
    from_value: str | None = None,
    to_value: str | None = None,
    field: str | None = None,
    note: str | None = None,
    employee_id: int = 1,
    employee_no: str = "EMP001",
    row_id: int = 1,
) -> EmployeeHistory:
    """Build a history row from a parsable ISO timestamp string."""
    occurred_dt = datetime.fromisoformat(occurred_at)
    return EmployeeHistory(
        id=row_id,
        employee_id=employee_id,
        employee_no=employee_no,
        event_type=event_type,
        from_value=from_value,
        to_value=to_value,
        field=field,
        note=note,
        occurred_at=occurred_dt,
    )


# ====================================================================
# log_event: must never raise from the logger path
# ====================================================================


class TestLogEvent:
    def test_returns_persisted_row_on_success(self, service, repo):
        repo.insert.return_value = _h(
            event_type=HistoryEventType.PROMOTED,
            occurred_at="2025-06-01T00:00:00+00:00",
        )
        result = service.log_event(
            employee_id=1, employee_no="EMP001",
            event_type=HistoryEventType.PROMOTED,
            from_value="Engineer",
            to_value="Senior Engineer",
        )
        assert result.event_type == HistoryEventType.PROMOTED
        repo.insert.assert_called_once()

    def test_does_not_raise_on_repo_failure(self, service, repo):
        """The audit path must NEVER break the primary write."""
        repo.insert.side_effect = Exception("DB down")
        result = service.log_event(
            employee_id=1, employee_no="EMP001",
            event_type=HistoryEventType.HIRED,
        )
        # Returned a sentinel row, not raised.
        assert result.id is None
        assert result.occurred_at is None
        assert result.event_type == HistoryEventType.HIRED


# ====================================================================
# get_history
# ====================================================================


class TestGetHistory:
    def test_returns_rows_from_repo(self, service, repo):
        rows = [_h(event_type=HistoryEventType.HIRED, occurred_at="2024-01-01T00:00:00+00:00")]
        repo.get_by_employee_no.return_value = rows
        result = service.get_history("EMP001")
        assert result == rows

    def test_wraps_repo_failure_in_service_error(self, service, repo):
        repo.get_by_employee_no.side_effect = Exception("DB down")
        with pytest.raises(ServiceError):
            service.get_history("EMP001")


# ====================================================================
# build_timeline / _compute_stats
# ====================================================================


class TestBuildTimelineBasic:
    def test_empty_history_returns_empty_timeline(self, service, repo):
        repo.get_by_employee_no.return_value = []
        timeline = service.build_timeline("EMP001")
        assert timeline.events == []
        assert timeline.stats.total_tenure_days == 0.0
        assert timeline.stats.promotions_count == 0
        assert timeline.stats.is_stalled is False
        # Threshold should still be stored for inspection.
        assert timeline.stats.stall_threshold_days == pytest.approx(365 * 4)


class TestComputeStats:
    def test_total_tenure_is_earliest_to_now(self, service, repo):
        # Hire 3 years ago, no promotions.
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = [
            _h(
                event_type=HistoryEventType.HIRED,
                occurred_at="2022-01-01T00:00:00+00:00",
                row_id=1,
            ),
        ]
        repo.get_by_employee_no.return_value = list(reversed(rows))
        # Reversed because the repo returns newest-first.
        timeline = service.build_timeline(
            "EMP001", full_name="Anya",
            now=now, stall_threshold_days=365 * 4,
        )
        # 3 years in days
        assert timeline.stats.total_tenure_days == pytest.approx(365 * 3, rel=0.01)

    def test_promotions_count(self, service, repo):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = [
            _h(event_type=HistoryEventType.HIRED,
               occurred_at="2020-01-01T00:00:00+00:00", row_id=1),
            _h(event_type=HistoryEventType.PROMOTED,
               occurred_at="2021-01-01T00:00:00+00:00",
               from_value="A", to_value="B", row_id=2),
            _h(event_type=HistoryEventType.PROMOTED,
               occurred_at="2023-01-01T00:00:00+00:00",
               from_value="B", to_value="C", row_id=3),
        ]
        repo.get_by_employee_no.return_value = list(reversed(rows))
        timeline = service.build_timeline("EMP001", now=now)
        assert timeline.stats.promotions_count == 2

    def test_time_since_last_promotion(self, service, repo):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = [
            _h(event_type=HistoryEventType.HIRED,
               occurred_at="2020-01-01T00:00:00+00:00", row_id=1),
            _h(event_type=HistoryEventType.PROMOTED,
               occurred_at="2023-01-01T00:00:00+00:00",
               from_value="A", to_value="B", row_id=2),
        ]
        repo.get_by_employee_no.return_value = list(reversed(rows))
        timeline = service.build_timeline("EMP001", now=now)
        # 2023-01-01 → 2025-01-01 = 2 years = 730 days
        assert timeline.stats.time_since_last_promotion_days == pytest.approx(730, rel=0.01)

    def test_time_since_last_promotion_none_if_never_promoted(
        self, service, repo,
    ):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = [_h(event_type=HistoryEventType.HIRED,
                   occurred_at="2020-01-01T00:00:00+00:00", row_id=1)]
        repo.get_by_employee_no.return_value = list(reversed(rows))
        timeline = service.build_timeline("EMP001", now=now)
        assert timeline.stats.time_since_last_promotion_days is None

    def test_average_time_between_promotions(self, service, repo):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = [
            _h(event_type=HistoryEventType.HIRED,
               occurred_at="2020-01-01T00:00:00+00:00", row_id=1),
            _h(event_type=HistoryEventType.PROMOTED,
               occurred_at="2021-01-01T00:00:00+00:00",
               from_value="A", to_value="B", row_id=2),
            _h(event_type=HistoryEventType.PROMOTED,
               occurred_at="2023-01-01T00:00:00+00:00",
               from_value="B", to_value="C", row_id=3),
        ]
        repo.get_by_employee_no.return_value = list(reversed(rows))
        timeline = service.build_timeline("EMP001", now=now)
        # First promo at 2021-01-01, last promo at 2023-01-01 → span 730 days,
        # 2 promotions, average = 730 / (2 - 1) = 730 days.
        assert timeline.stats.average_time_between_promotions_days == pytest.approx(730, rel=0.01)

    def test_average_between_promotions_none_for_single_promotion(
        self, service, repo,
    ):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = [
            _h(event_type=HistoryEventType.HIRED,
               occurred_at="2020-01-01T00:00:00+00:00", row_id=1),
            _h(event_type=HistoryEventType.PROMOTED,
               occurred_at="2023-01-01T00:00:00+00:00",
               from_value="A", to_value="B", row_id=2),
        ]
        repo.get_by_employee_no.return_value = list(reversed(rows))
        timeline = service.build_timeline("EMP001", now=now)
        assert timeline.stats.average_time_between_promotions_days is None


class TestStallDetection:
    def test_stalled_when_over_threshold(self, service, repo):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = [
            _h(event_type=HistoryEventType.HIRED,
               occurred_at="2010-01-01T00:00:00+00:00", row_id=1),
            _h(event_type=HistoryEventType.PROMOTED,
               occurred_at="2011-01-01T00:00:00+00:00",
               from_value="A", to_value="B", row_id=2),
        ]
        repo.get_by_employee_no.return_value = list(reversed(rows))
        timeline = service.build_timeline(
            "EMP001", now=now, stall_threshold_days=365 * 4,
        )
        # Last promotion was 14 years ago — well over 4.
        assert timeline.stats.is_stalled is True

    def test_not_stalled_when_under_threshold(self, service, repo):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = [
            _h(event_type=HistoryEventType.HIRED,
               occurred_at="2020-01-01T00:00:00+00:00", row_id=1),
            _h(event_type=HistoryEventType.PROMOTED,
               occurred_at="2024-01-01T00:00:00+00:00",
               from_value="A", to_value="B", row_id=2),
        ]
        repo.get_by_employee_no.return_value = list(reversed(rows))
        timeline = service.build_timeline(
            "EMP001", now=now, stall_threshold_days=365 * 4,
        )
        # Last promotion was 1 year ago — under 4-year threshold.
        assert timeline.stats.is_stalled is False

    def test_not_stalled_when_never_promoted(self, service, repo):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = [_h(event_type=HistoryEventType.HIRED,
                   occurred_at="2020-01-01T00:00:00+00:00", row_id=1)]
        repo.get_by_employee_no.return_value = list(reversed(rows))
        timeline = service.build_timeline(
            "EMP001", now=now, stall_threshold_days=365 * 4,
        )
        # Never promoted → can't be "stalled" on the time-since-promo axis.
        assert timeline.stats.is_stalled is False


class TestTimeInEachRole:
    def test_durations_assigned_to_named_roles(self, service, repo):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = [
            _h(event_type=HistoryEventType.HIRED,
               occurred_at="2020-01-01T00:00:00+00:00",
               to_value="Engineer", row_id=1),
            _h(event_type=HistoryEventType.PROMOTED,
               occurred_at="2022-01-01T00:00:00+00:00",
               from_value="Engineer", to_value="Senior", row_id=2),
            _h(event_type=HistoryEventType.PROMOTED,
               occurred_at="2024-01-01T00:00:00+00:00",
               from_value="Senior", to_value="Staff", row_id=3),
        ]
        repo.get_by_employee_no.return_value = list(reversed(rows))
        timeline = service.build_timeline("EMP001", now=now)
        roles = timeline.stats.time_in_each_role
        # Engineer: 2020-01-01 → 2022-01-01 ≈ 730 days
        # Senior:   2022-01-01 → 2024-01-01 ≈ 730 days
        # Staff:    2024-01-01 → 2025-01-01 ≈ 365 days
        assert "Engineer" in roles
        assert "Senior" in roles
        assert "Staff" in roles
        assert roles["Engineer"] == pytest.approx(730, rel=0.01)
        assert roles["Senior"] == pytest.approx(730, rel=0.01)
        assert roles["Staff"] == pytest.approx(365, rel=0.01)


class TestTimelineOrder:
    def test_events_are_chronological_oldest_first(self, service, repo):
        rows = [
            _h(event_type=HistoryEventType.HIRED,
               occurred_at="2020-01-01T00:00:00+00:00", row_id=1),
            _h(event_type=HistoryEventType.PROMOTED,
               occurred_at="2022-01-01T00:00:00+00:00",
               from_value="A", to_value="B", row_id=2),
            _h(event_type=HistoryEventType.PROMOTED,
               occurred_at="2024-01-01T00:00:00+00:00",
               from_value="B", to_value="C", row_id=3),
        ]
        # Simulate DB newest-first ordering.
        repo.get_by_employee_no.return_value = list(reversed(rows))
        timeline = service.build_timeline("EMP001")
        # Expected chronological order.
        assert timeline.events[0].event_type == HistoryEventType.HIRED
        assert timeline.events[1].to_value == "B"
        assert timeline.events[2].to_value == "C"
