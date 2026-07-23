"""
Shared models and enums for the HR AI Assistant.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class EmploymentStatus(str, Enum):
    """Employment status."""

    ACTIVE = "Active"
    INACTIVE = "Inactive"
    TERMINATED = "Terminated"
    ON_LEAVE = "On Leave"


class EmploymentType(str, Enum):
    """Employment type."""

    FULL_TIME = "Full Time"
    PART_TIME = "Part Time"
    INTERN = "Intern"
    CONTRACT = "Contract"


class Gender(str, Enum):
    """Gender."""

    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    PREFER_NOT_TO_SAY = "Prefer Not To Say"


class BaseSchema(BaseModel):
    """
    Base model inherited by every schema.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="forbid",
        validate_assignment=True,
    )


class TimestampMixin(BaseSchema):
    """
    Shared timestamp model.
    """

    created_at: datetime | None = None