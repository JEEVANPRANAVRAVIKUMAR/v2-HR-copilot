"""
Response models used across the application.
"""

from __future__ import annotations

from datetime import date, datetime

from models.common import BaseSchema


class EmployeeProfileResponse(BaseSchema):
    """
    Complete employee profile returned by repository methods.
    """

    employee_no: str
    full_name: str
    created_at: datetime | None = None
    is_active: bool

    # Personal Profile
    dob: date | None = None
    gender: str | None = None
    nationality: str | None = None
    marital_status: str | None = None
    blood_group: str | None = None

    # Contact
    email: str | None = None
    phone: str | None = None

    # Address
    city: str | None = None
    full_address: str | None = None

    # Employment
    employment_type: str | None = None
    joining_date: date | None = None
    status: str | None = None
    work_location: str | None = None

    # Current Position
    department: str | None = None
    position_title: str | None = None