"""
Tests for the EmployeeHistoryRepository.

Uses the same mock-client pattern as ``test_employee_repository``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from database.client import DatabaseClient
from database.queries import EmployeeHistoryRepository
from models.history import EmployeeHistoryCreate, HistoryEventType
from utils.exceptions import RepositoryError


@pytest.fixture
def mock_client():
    mock = MagicMock()
    with patch.object(DatabaseClient, "get_client", return_value=mock):
        yield mock
    DatabaseClient.reset()


@pytest.fixture
def repo(mock_client):
    return EmployeeHistoryRepository()


def _row(**overrides):
    base = {
        "id": 1,
        "employee_id": 10,
        "employee_no": "EMP010",
        "event_type": "promoted",
        "from_value": "Engineer",
        "to_value": "Senior Engineer",
        "field": "position_title",
        "note": None,
        "occurred_at": "2025-06-01T10:00:00+00:00",
    }
    base.update(overrides)
    return base


# ====================================================================
# insert
# ====================================================================


class TestInsert:
    def test_insert_returns_validated_history(self, repo, mock_client):
        mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[_row()]
        )
        event = EmployeeHistoryCreate(
            employee_id=10,
            employee_no="EMP010",
            event_type=HistoryEventType.PROMOTED,
            from_value="Engineer",
            to_value="Senior Engineer",
            field="position_title",
        )
        result = repo.insert(event)
        assert result.event_type == HistoryEventType.PROMOTED
        assert result.employee_no == "EMP010"
        assert result.to_value == "Senior Engineer"

    def test_insert_wraps_failure_in_repository_error(self, repo, mock_client):
        mock_client.table.side_effect = Exception("DB down")
        event = EmployeeHistoryCreate(
            employee_id=10, employee_no="EMP010",
            event_type=HistoryEventType.HIRED,
        )
        with pytest.raises(RepositoryError):
            repo.insert(event)

    def test_insert_raises_repository_error_when_no_rows(self, repo, mock_client):
        mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[]
        )
        event = EmployeeHistoryCreate(
            employee_id=10, employee_no="EMP010",
            event_type=HistoryEventType.HIRED,
        )
        with pytest.raises(RepositoryError):
            repo.insert(event)


# ====================================================================
# insert_many
# ====================================================================


class TestInsertMany:
    def test_empty_returns_empty(self, repo, mock_client):
        assert repo.insert_many([]) == []
        mock_client.table.assert_not_called()

    def test_insert_many_returns_rows(self, repo, mock_client):
        rows = [
            _row(id=1, event_type="hired"),
            _row(id=2, event_type="promoted"),
        ]
        mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=rows
        )
        events = [
            EmployeeHistoryCreate(
                employee_id=10, employee_no="EMP010",
                event_type=HistoryEventType.HIRED,
            ),
            EmployeeHistoryCreate(
                employee_id=10, employee_no="EMP010",
                event_type=HistoryEventType.PROMOTED,
                from_value="Engineer",
                to_value="Senior Engineer",
            ),
        ]
        result = repo.insert_many(events)
        assert len(result) == 2
        assert result[0].event_type == HistoryEventType.HIRED
        assert result[1].event_type == HistoryEventType.PROMOTED


# ====================================================================
# get_by_employee_no
# ====================================================================


class TestGetByEmployeeNo:
    def test_returns_validated_rows(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[_row(id=2, event_type="promoted"), _row(id=1, event_type="hired")]
        )
        result = repo.get_by_employee_no("EMP010")
        assert len(result) == 2
        assert result[0].event_type == HistoryEventType.PROMOTED
        assert result[1].event_type == HistoryEventType.HIRED

    def test_returns_empty_list_when_no_rows(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[]
        )
        assert repo.get_by_employee_no("EMP999") == []

    def test_wraps_failure_in_repository_error(self, repo, mock_client):
        mock_client.table.side_effect = Exception("DB down")
        with pytest.raises(RepositoryError):
            repo.get_by_employee_no("EMP010")


# ====================================================================
# get_latest_promotion
# ====================================================================


class TestGetLatestPromotion:
    def test_returns_most_recent_promotion(self, repo, mock_client):
        expected = _row(id=3, event_type="promoted", occurred_at="2025-12-01T00:00:00+00:00")
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[expected]
        )
        result = repo.get_latest_promotion("EMP010")
        assert result is not None
        assert result.event_type == HistoryEventType.PROMOTED

    def test_returns_none_when_never_promoted(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        assert repo.get_latest_promotion("EMP010") is None


# ====================================================================
# get_events_by_type
# ====================================================================


class TestGetEventsByType:
    def test_returns_validated_rows_by_type(self, repo, mock_client):
        rows = [_row(id=1, event_type="hired"), _row(id=2, event_type="hired")]
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=rows
        )
        result = repo.get_events_by_type("hired")
        assert len(result) == 2
        assert all(r.event_type == HistoryEventType.HIRED for r in result)
