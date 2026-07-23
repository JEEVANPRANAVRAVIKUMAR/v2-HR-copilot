"""
Tests for EmployeeRepository.

Covers happy path and key error cases for every method.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.employee import Employee, EmployeeCreate, EmployeeUpdate
from utils.exceptions import RepositoryError

from .conftest import make_employee_row, make_mock_response


# ====================================================================
# exists
# ====================================================================


class TestExists:
    def test_returns_true_when_employee_exists(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq.return_value \
            .limit.return_value.execute.return_value = make_mock_response(
                [{"employee_no": "EMP001"}]
            )
        assert repo.exists("EMP001") is True

    def test_returns_false_when_employee_does_not_exist(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq.return_value \
            .limit.return_value.execute.return_value = make_mock_response([])
        assert repo.exists("EMP001") is False

    def test_raises_repository_error_on_db_failure(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq.return_value \
            .limit.return_value.execute.side_effect = Exception("DB down")
        with pytest.raises(RepositoryError):
            repo.exists("EMP001")


# ====================================================================
# get_by_id
# ====================================================================


class TestGetById:
    def test_returns_employee_when_found(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq \
            .return_value.limit.return_value.execute.return_value \
            = make_mock_response([make_employee_row(employee_id=42)])
        result = repo.get_by_id(42)
        assert isinstance(result, Employee)
        assert result.id == 42
        assert result.employee_no == "EMP001"

    def test_returns_none_when_not_found(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq \
            .return_value.limit.return_value.execute.return_value \
            = make_mock_response([])
        assert repo.get_by_id(99) is None

    def test_raises_repository_error_on_db_failure(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq \
            .return_value.limit.return_value.execute.side_effect \
            = Exception("DB down")
        with pytest.raises(RepositoryError):
            repo.get_by_id(1)


# ====================================================================
# get_by_employee_no
# ====================================================================


class TestGetByEmployeeNo:
    def test_returns_employee_when_found(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq \
            .return_value.limit.return_value.execute.return_value \
            = make_mock_response([make_employee_row()])
        result = repo.get_by_employee_no("EMP001")
        assert isinstance(result, Employee)
        assert result.employee_no == "EMP001"
        assert result.full_name == "John Doe"

    def test_returns_none_when_not_found(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq \
            .return_value.limit.return_value.execute.return_value \
            = make_mock_response([])
        assert repo.get_by_employee_no("MISSING") is None

    def test_raises_repository_error_on_db_failure(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq \
            .return_value.limit.return_value.execute.side_effect \
            = Exception("DB down")
        with pytest.raises(RepositoryError):
            repo.get_by_employee_no("EMP001")


# ====================================================================
# get_by_name
# ====================================================================


class TestGetByName:
    def test_returns_matching_employees(self, repo, mock_client):
        rows = [
            make_employee_row(employee_no="EMP001", full_name="John Doe"),
            make_employee_row(employee_no="EMP002", full_name="John Smith"),
        ]
        mock_client.table.return_value.select.return_value.ilike \
            .return_value.execute.return_value = make_mock_response(rows)
        results = repo.get_by_name("John")
        assert len(results) == 2
        assert all(isinstance(e, Employee) for e in results)

    def test_returns_empty_list_when_no_match(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.ilike \
            .return_value.execute.return_value = make_mock_response([])
        assert repo.get_by_name("Xyz") == []

    def test_raises_repository_error_on_db_failure(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.ilike \
            .return_value.execute.side_effect = Exception("DB down")
        with pytest.raises(RepositoryError):
            repo.get_by_name("John")


# ====================================================================
# get_all
# ====================================================================


class TestGetAll:
    def test_returns_all_employees(self, repo, mock_client):
        rows = [
            make_employee_row(employee_no="EMP001"),
            make_employee_row(employee_no="EMP002"),
        ]
        mock_client.table.return_value.select.return_value.order \
            .return_value.execute.return_value = make_mock_response(rows)
        results = repo.get_all()
        assert len(results) == 2
        assert all(isinstance(e, Employee) for e in results)

    def test_returns_empty_list_when_no_data(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.order \
            .return_value.execute.return_value = make_mock_response([])
        assert repo.get_all() == []

    def test_raises_repository_error_on_db_failure(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.order \
            .return_value.execute.side_effect = Exception("DB down")
        with pytest.raises(RepositoryError):
            repo.get_all()


# ====================================================================
# search
# ====================================================================


class TestSearch:
    def test_search_with_text_query(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.or_ \
            .return_value.order.return_value.execute.return_value \
            = make_mock_response([make_employee_row()])
        results = repo.search(query="EMP")
        assert len(results) == 1

    def test_search_with_is_active_filter(self, repo, mock_client):
        query_chain = (
            mock_client.table.return_value.select.return_value
        )
        query_chain.eq.return_value.order.return_value.execute \
            .return_value = make_mock_response([make_employee_row()])
        results = repo.search(is_active=True)
        assert len(results) == 1

    def test_search_no_filters_returns_all(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.order \
            .return_value.execute.return_value = make_mock_response(
                [make_employee_row()]
            )
        results = repo.search()
        assert len(results) == 1

    def test_raises_repository_error_on_db_failure(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.order \
            .return_value.execute.side_effect = Exception("DB down")
        with pytest.raises(RepositoryError):
            repo.search()


# ====================================================================
# create
# ====================================================================


class TestCreate:
    def test_creates_employee_successfully(self, repo, mock_client):
        data = EmployeeCreate(employee_no="EMP003", full_name="New Hire")
        mock_client.table.return_value.insert.return_value \
            .execute.return_value = make_mock_response(
                [make_employee_row(employee_no="EMP003", full_name="New Hire")]
            )
        result = repo.create(data)
        assert isinstance(result, Employee)
        assert result.employee_no == "EMP003"
        assert result.full_name == "New Hire"

    def test_raises_repository_error_when_insert_fails(self, repo, mock_client):
        data = EmployeeCreate(employee_no="EMP003", full_name="New Hire")
        mock_client.table.return_value.insert.return_value \
            .execute.return_value = make_mock_response([])
        with pytest.raises(RepositoryError):
            repo.create(data)

    def test_raises_repository_error_on_db_failure(self, repo, mock_client):
        data = EmployeeCreate(employee_no="EMP003", full_name="New Hire")
        mock_client.table.return_value.insert.return_value \
            .execute.side_effect = Exception("DB down")
        with pytest.raises(RepositoryError):
            repo.create(data)


# ====================================================================
# update
# ====================================================================


class TestUpdate:
    def test_updates_employee_successfully(self, repo, mock_client):
        data = EmployeeUpdate(full_name="Updated Name")
        mock_client.table.return_value.update.return_value.eq \
            .return_value.execute.return_value = make_mock_response(
                [make_employee_row(full_name="Updated Name")]
            )
        result = repo.update("EMP001", data)
        assert isinstance(result, Employee)
        assert result.full_name == "Updated Name"

    def test_raises_repository_error_when_update_returns_no_data(
        self, repo, mock_client
    ):
        data = EmployeeUpdate(full_name="Updated Name")
        mock_client.table.return_value.update.return_value.eq \
            .return_value.execute.return_value = make_mock_response([])
        with pytest.raises(RepositoryError):
            repo.update("EMP001", data)

    def test_raises_repository_error_on_db_failure(self, repo, mock_client):
        data = EmployeeUpdate(full_name="Updated Name")
        mock_client.table.return_value.update.return_value.eq \
            .return_value.execute.side_effect = Exception("DB down")
        with pytest.raises(RepositoryError):
            repo.update("EMP001", data)


# ====================================================================
# activate / deactivate / delete
# ====================================================================


class TestActivate:
    def test_activates_employee(self, repo, mock_client):
        data = {"is_active": True}
        mock_client.table.return_value.update.return_value.eq \
            .return_value.execute.return_value = make_mock_response(
                [make_employee_row(is_active=True)]
            )
        result = repo.activate("EMP001")
        assert isinstance(result, Employee)
        assert result.is_active is True


class TestDeactivate:
    def test_deactivates_employee(self, repo, mock_client):
        mock_client.table.return_value.update.return_value.eq \
            .return_value.execute.return_value = make_mock_response(
                [make_employee_row(is_active=False)]
            )
        result = repo.deactivate("EMP001")
        assert isinstance(result, Employee)
        assert result.is_active is False


class TestDelete:
    def test_soft_deletes_employee(self, repo, mock_client):
        mock_client.table.return_value.update.return_value.eq \
            .return_value.execute.return_value = make_mock_response(
                [make_employee_row(is_active=False)]
            )
        result = repo.delete("EMP001")
        assert isinstance(result, Employee)
        assert result.is_active is False


# ====================================================================
# get_full_profile
# ====================================================================


class TestGetFullProfile:
    def test_returns_full_profile_when_found(self, repo, mock_client):
        row = make_employee_row()
        row["employee_profiles"] = [
            {
                "dob": "1990-01-15",
                "gender": "Male",
                "nationality": "US",
                "marital_status": "Single",
                "blood_group": "O+",
            }
        ]
        row["contact_info"] = [
            {"email": "john@example.com", "phone": "555-0100"}
        ]
        row["addresses"] = [
            {"city": "New York", "full_address": "123 Main St"}
        ]
        row["employment_details"] = [
            {
                "employment_type": "Full Time",
                "joining_date": "2025-01-01",
                "status": "Active",
                "work_location": "NYC Office",
            }
        ]
        row["position_history"] = [
            {
                "department": "Engineering",
                "position_title": "Software Engineer",
                "effective_date": "2025-06-01",
            }
        ]
        mock_client.table.return_value.select.return_value.eq \
            .return_value.limit.return_value.execute.return_value \
            = make_mock_response([row])
        profile = repo.get_full_profile("EMP001")
        assert profile is not None
        assert profile.employee_no == "EMP001"
        assert profile.full_name == "John Doe"
        assert profile.gender == "Male"
        assert profile.email == "john@example.com"
        assert profile.city == "New York"
        assert profile.employment_type == "Full Time"
        assert profile.department == "Engineering"
        assert profile.position_title == "Software Engineer"

    def test_returns_none_when_not_found(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq \
            .return_value.limit.return_value.execute.return_value \
            = make_mock_response([])
        assert repo.get_full_profile("MISSING") is None

    def test_handles_missing_related_tables_gracefully(
        self, repo, mock_client
    ):
        row = make_employee_row()
        row["employee_profiles"] = []
        row["contact_info"] = []
        row["addresses"] = []
        row["employment_details"] = []
        row["position_history"] = []
        mock_client.table.return_value.select.return_value.eq \
            .return_value.limit.return_value.execute.return_value \
            = make_mock_response([row])
        profile = repo.get_full_profile("EMP001")
        assert profile is not None
        assert profile.employee_no == "EMP001"
        assert profile.gender is None
        assert profile.department is None

    def test_raises_repository_error_on_db_failure(self, repo, mock_client):
        mock_client.table.return_value.select.return_value.eq \
            .return_value.limit.return_value.execute.side_effect \
            = Exception("DB down")
        with pytest.raises(RepositoryError):
            repo.get_full_profile("EMP001")
