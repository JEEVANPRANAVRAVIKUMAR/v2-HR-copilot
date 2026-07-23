"""
Employee models.
"""

from __future__ import annotations

from datetime import datetime

from models.common import BaseSchema, TimestampMixin


class EmployeeCreate(BaseSchema):
    """
    Request model for creating an employee.
    """

    employee_no: str
    full_name: str
    is_active: bool = True


class EmployeeUpdate(BaseSchema):
    """
    Request model for updating employee information.
    """

    full_name: str | None = None
    is_active: bool | None = None


class Employee(TimestampMixin):
    """
    Employee database model.
    """

    id: int | None = None
    employee_no: str
    full_name: str
    is_active: bool
    updated_at: datetime | None = None