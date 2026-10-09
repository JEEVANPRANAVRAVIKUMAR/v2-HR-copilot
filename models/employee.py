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
    is_active: bool = True
    updated_at: datetime | None = None

    # Joined fields
    department: str | None = None
    position_title: str | None = None
    email: str | None = None
    phone: str | None = None
    status: str | None = None
    employment_type: str | None = None
    work_location: str | None = None
    joining_date: str | None = None
    city: str | None = None
    full_address: str | None = None
    dob: str | None = None
    gender: str | None = None
    nationality: str | None = None
    marital_status: str | None = None
    blood_group: str | None = None