"""
Tests for CrudAgent.
"""

from __future__ import annotations

import json
from logging import Logger
from unittest.mock import create_autospec

import pytest

from ai import CrudAgent, GroqLLM
from models.employee import Employee
from services import EmployeeService
from utils.exceptions import ServiceError


@pytest.fixture
def llm():
    return create_autospec(GroqLLM, instance=True)


@pytest.fixture
def employee_service():
    return create_autospec(EmployeeService, instance=True)


@pytest.fixture
def logger():
    return create_autospec(Logger, instance=True)


@pytest.fixture
def agent(llm, employee_service, logger):
    return CrudAgent(
        llm=llm,
        employee_service=employee_service,
        logger=logger,
    )


def _make_json_response(data: dict) -> str:
    return json.dumps(data)


# ====================================================================
# Lookup
# ====================================================================


class TestLookup:
    def test_lookup_by_employee_no(self, agent, llm, employee_service):
        llm.generate.return_value = _make_json_response({
            "operation": "lookup",
            "fields": {"employee_no": "EMP001"},
            "missing_fields": [],
            "clarification_needed": None,
            "ready_to_confirm": False,
        })
        emp = Employee.model_validate({
            "employee_no": "EMP001",
            "full_name": "John Doe",
            "is_active": True,
            "created_at": "2025-01-01T00:00:00",
            "id": 1,
        })
        employee_service.get_employee_by_no.return_value = emp

        result = agent.process("Show me EMP001")
        assert "John Doe" in result
        assert "EMP001" in result

    def test_lookup_not_found(self, agent, llm, employee_service):
        llm.generate.return_value = _make_json_response({
            "operation": "lookup",
            "fields": {"employee_no": "MISSING"},
            "missing_fields": [],
            "clarification_needed": None,
            "ready_to_confirm": False,
        })
        employee_service.get_employee_by_no.return_value = None

        result = agent.process("Show me MISSING")
        assert "not found" in result

    def test_falls_back_to_name_lookup_when_llm_operation_is_unknown(
        self, agent, llm, employee_service,
    ):
        llm.generate.return_value = _make_json_response({
            "operation": "unknown",
            "fields": {},
        })
        emp = Employee.model_validate({
            "employee_no": "EMP0104",
            "full_name": "Vikram Singh",
            "is_active": True,
            "id": 104,
        })
        employee_service.search_employees.return_value = [emp]

        result = agent.process("who is vikram singh")

        assert "Vikram Singh" in result
        employee_service.search_employees.assert_called_with(query="vikram singh")


# ====================================================================
# Create
# ====================================================================


class TestCreate:
    def test_creates_employee(self, agent, llm, employee_service):
        llm.generate.return_value = _make_json_response({
            "operation": "create",
            "fields": {
                "employee_no": "EMP010",
                "full_name": "Rahul Sharma",
            },
            "missing_fields": [],
            "clarification_needed": None,
            "ready_to_confirm": True,
        })
        emp = Employee.model_validate({
            "employee_no": "EMP010",
            "full_name": "Rahul Sharma",
            "is_active": True,
            "id": 10,
        })
        employee_service.create_employee.return_value = emp

        result = agent.process("Hire Rahul Sharma as EMP010")
        assert "Rahul Sharma" in result
        assert "EMP010" in result
        employee_service.create_employee.assert_called_once()

    def test_asks_for_missing_fields(self, agent, llm):
        llm.generate.return_value = _make_json_response({
            "operation": "create",
            "fields": {},
            "missing_fields": ["employee_no", "full_name"],
            "clarification_needed": "I need the employee's name and number.",
            "ready_to_confirm": False,
        })
        result = agent.process("Hire someone")
        assert "name" in result.lower() or "number" in result.lower()


# ====================================================================
# Update / Activate / Deactivate
# ====================================================================


class TestUpdate:
    def test_updates_employee(self, agent, llm, employee_service):
        llm.generate.return_value = _make_json_response({
            "operation": "update",
            "fields": {"employee_no": "EMP001", "full_name": "John Updated"},
            "missing_fields": [],
            "clarification_needed": None,
            "ready_to_confirm": True,
        })
        emp = Employee.model_validate({
            "employee_no": "EMP001",
            "full_name": "John Updated",
            "is_active": True,
            "id": 1,
        })
        employee_service.update_employee.return_value = emp

        result = agent.process("Update EMP001 name to John Updated")
        assert "John Updated" in result
        employee_service.update_employee.assert_called_once()


class TestActivateDeactivate:
    def test_activates(self, agent, llm, employee_service):
        llm.generate.return_value = _make_json_response({
            "operation": "activate",
            "fields": {"employee_no": "EMP001"},
            "missing_fields": [],
            "clarification_needed": None,
            "ready_to_confirm": True,
        })
        result = agent.process("Activate EMP001")
        assert "activated" in result.lower()
        employee_service.activate_employee.assert_called_once_with("EMP001")

    def test_deactivates(self, agent, llm, employee_service):
        llm.generate.return_value = _make_json_response({
            "operation": "deactivate",
            "fields": {"employee_no": "EMP001"},
            "missing_fields": [],
            "clarification_needed": None,
            "ready_to_confirm": True,
        })
        result = agent.process("Deactivate EMP001")
        assert "deactivated" in result.lower()
        employee_service.deactivate_employee.assert_called_once_with("EMP001")

    def test_asks_for_employee_no_when_missing(self, agent, llm):
        llm.generate.return_value = _make_json_response({
            "operation": "activate",
            "fields": {},
            "missing_fields": ["employee_no"],
            "clarification_needed": None,
            "ready_to_confirm": False,
        })
        result = agent.process("Activate someone")
        assert "employee number" in result.lower() or "which" in result.lower()


class TestErrors:
    def test_wraps_unexpected_error(self, agent, llm, employee_service):
        llm.generate.side_effect = Exception("Boom")
        with pytest.raises(ServiceError):
            agent.process("Hire someone")
