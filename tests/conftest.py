"""
Shared test fixtures and configuration.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from database.client import DatabaseClient
from database.queries import EmployeeRepository
from models.employee import Employee


def make_mock_response(data: list) -> MagicMock:
    """Create a mock Supabase response with the given data."""
    response = MagicMock()
    response.data = data
    return response


def make_employee_row(
    *,
    employee_no: str = "EMP001",
    full_name: str = "John Doe",
    is_active: bool = True,
    employee_id: int = 1,
    created_at: str | None = "2025-01-01T00:00:00",
    updated_at: str | None = None,
) -> dict:
    """Build a raw employee dict as returned by Supabase."""
    row = {
        "id": employee_id,
        "employee_no": employee_no,
        "full_name": full_name,
        "is_active": is_active,
        "created_at": created_at,
        "updated_at": updated_at,
    }
    return row


@pytest.fixture
def mock_client():
    """
    Fixture that replaces the DatabaseClient singleton with
    a mock and resets it after the test.
    """
    mock = MagicMock()
    with patch.object(
        DatabaseClient, "get_client", return_value=mock
    ):
        yield mock
    DatabaseClient.reset()


@pytest.fixture
def repo(mock_client):
    """Fixture providing an EmployeeRepository bound to the mock client."""
    return EmployeeRepository()
