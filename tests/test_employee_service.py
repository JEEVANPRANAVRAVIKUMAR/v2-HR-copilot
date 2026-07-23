"""
Tests for EmployeeService.

Covers business rule enforcement, error wrapping, and logging.
"""

from __future__ import annotations

from logging import Logger
from unittest.mock import MagicMock, create_autospec

import pytest

from database.queries import EmployeeRepository
from models.employee import Employee, EmployeeCreate, EmployeeUpdate
from services import EmployeeService
from utils.exceptions import (
    DuplicateEmployeeError,
    EmployeeNotFoundError,
    ServiceError,
    ValidationError,
)

from .conftest import make_employee_row


@pytest.fixture
def repo():
    return create_autospec(EmployeeRepository, instance=True)


@pytest.fixture
def logger():
    return create_autospec(Logger, instance=True)


@pytest.fixture
def service(repo, logger):
    return EmployeeService(repository=repo, logger=logger)


def _make_employee(**overrides) -> Employee:
    fields = dict(make_employee_row(**overrides))
    return Employee.model_validate(fields)


# ====================================================================
# create_employee
# ====================================================================


class TestCreateEmployee:
    def test_creates_employee_when_no_duplicate(self, service, repo):
        repo.exists.return_value = False
        expected = _make_employee(employee_no="EMP001")
        repo.create.return_value = expected

        result = service.create_employee(
            EmployeeCreate(employee_no="EMP001", full_name="John")
        )
        assert result.employee_no == "EMP001"
        repo.create.assert_called_once()

    def test_raises_duplicate_error_when_employee_exists(
        self, service, repo
    ):
        repo.exists.return_value = True
        with pytest.raises(DuplicateEmployeeError):
            service.create_employee(
                EmployeeCreate(employee_no="EMP001", full_name="John")
            )
        repo.create.assert_not_called()

    def test_wraps_unexpected_error(self, service, repo):
        repo.exists.return_value = False
        repo.create.side_effect = Exception("Unexpected")
        with pytest.raises(ServiceError):
            service.create_employee(
                EmployeeCreate(employee_no="EMP001", full_name="John")
            )


# ====================================================================
# get_employee_by_id / get_employee_by_no
# ====================================================================


class TestGetEmployee:
    def test_get_by_id_returns_employee(self, service, repo):
        expected = _make_employee()
        repo.get_by_id.return_value = expected
        result = service.get_employee_by_id(1)
        assert result == expected

    def test_get_by_id_returns_none(self, service, repo):
        repo.get_by_id.return_value = None
        assert service.get_employee_by_id(99) is None

    def test_get_by_id_wraps_error(self, service, repo):
        repo.get_by_id.side_effect = Exception("DB down")
        with pytest.raises(ServiceError):
            service.get_employee_by_id(1)

    def test_get_by_no_returns_employee(self, service, repo):
        expected = _make_employee()
        repo.get_by_employee_no.return_value = expected
        result = service.get_employee_by_no("EMP001")
        assert result == expected

    def test_get_by_no_returns_none(self, service, repo):
        repo.get_by_employee_no.return_value = None
        assert service.get_employee_by_no("MISSING") is None


# ====================================================================
# search_employees / list_all_employees
# ====================================================================


class TestSearchAndList:
    def test_search_returns_results(self, service, repo):
        results = [_make_employee()]
        repo.search.return_value = results
        assert service.search_employees(query="John") == results

    def test_search_wraps_error(self, service, repo):
        repo.search.side_effect = Exception("DB down")
        with pytest.raises(ServiceError):
            service.search_employees(query="John")

    def test_list_all_returns_employees(self, service, repo):
        results = [_make_employee(), _make_employee(employee_no="EMP002")]
        repo.get_all.return_value = results
        assert service.list_all_employees() == results


# ====================================================================
# get_full_profile
# ====================================================================


class TestGetFullProfile:
    def test_returns_profile(self, service, repo):
        from models.responses import EmployeeProfileResponse
        profile = EmployeeProfileResponse(
            employee_no="EMP001", full_name="John", is_active=True
        )
        repo.get_full_profile.return_value = profile
        result = service.get_full_profile("EMP001")
        assert result == profile

    def test_returns_none(self, service, repo):
        repo.get_full_profile.return_value = None
        assert service.get_full_profile("MISSING") is None


# ====================================================================
# update_employee
# ====================================================================


class TestUpdateEmployee:
    def test_updates_when_employee_exists(self, service, repo):
        repo.get_by_employee_no.return_value = _make_employee()
        expected = _make_employee(full_name="Updated")
        repo.update.return_value = expected

        result = service.update_employee(
            "EMP001", EmployeeUpdate(full_name="Updated")
        )
        assert result.full_name == "Updated"

    def test_raises_not_found_when_missing(self, service, repo):
        repo.get_by_employee_no.return_value = None
        with pytest.raises(EmployeeNotFoundError):
            service.update_employee(
                "MISSING", EmployeeUpdate(full_name="Nope")
            )

    def test_raises_validation_error_when_no_fields(self, service, repo):
        with pytest.raises(ValidationError):
            service.update_employee("EMP001", EmployeeUpdate())

    def test_wraps_unexpected_error(self, service, repo):
        repo.get_by_employee_no.return_value = _make_employee()
        repo.update.side_effect = Exception("Unexpected")
        with pytest.raises(ServiceError):
            service.update_employee(
                "EMP001", EmployeeUpdate(full_name="Test")
            )


# ====================================================================
# activate / deactivate / delete
# ====================================================================


class TestStatusTransitions:
    def test_activate(self, service, repo):
        repo.get_by_employee_no.return_value = _make_employee()
        expected = _make_employee(is_active=True)
        repo.activate.return_value = expected
        result = service.activate_employee("EMP001")
        assert result.is_active is True

    def test_deactivate(self, service, repo):
        repo.get_by_employee_no.return_value = _make_employee()
        expected = _make_employee(is_active=False)
        repo.deactivate.return_value = expected
        result = service.deactivate_employee("EMP001")
        assert result.is_active is False

    def test_delete_soft(self, service, repo):
        repo.get_by_employee_no.return_value = _make_employee()
        expected = _make_employee(is_active=False)
        repo.delete.return_value = expected
        result = service.delete_employee("EMP001")
        assert result.is_active is False

    def test_activate_not_found(self, service, repo):
        repo.get_by_employee_no.return_value = None
        with pytest.raises(EmployeeNotFoundError):
            service.activate_employee("MISSING")

    def test_deactivate_not_found(self, service, repo):
        repo.get_by_employee_no.return_value = None
        with pytest.raises(EmployeeNotFoundError):
            service.deactivate_employee("MISSING")
