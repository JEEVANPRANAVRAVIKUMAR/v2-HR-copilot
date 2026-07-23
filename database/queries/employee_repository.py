"""
Employee repository.

Handles all employee-related database operations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List

from core.constants import (
    ADDRESSES_TABLE,
    CONTACT_INFO_TABLE,
    EMPLOYEES_TABLE,
    EMPLOYMENT_DETAILS_TABLE,
    EMPLOYEE_PROFILES_TABLE,
    POSITION_HISTORY_TABLE,
)
from database.queries.base_repository import BaseRepository
from models.employee import Employee, EmployeeCreate, EmployeeUpdate
from models.responses import EmployeeProfileResponse
from utils.exceptions import RepositoryError


class EmployeeRepository(BaseRepository):
    """
    Repository responsible for employee CRUD operations.
    """

    def exists(self, employee_no: str) -> bool:
        """
        Check whether an employee exists.

        Args:
            employee_no: Employee number.

        Returns:
            True if employee exists.
        """
        try:
            response = self._execute(
                self.client
                .table(EMPLOYEES_TABLE)
                .select("employee_no")
                .eq("employee_no", employee_no)
                .limit(1)
            )
            return self._has_data(response)

        except Exception as exc:
            self.logger.exception("Failed checking employee existence.")
            raise RepositoryError("Unable to verify employee.") from exc

    def get_by_id(self, employee_id: int) -> Employee | None:
        """
        Retrieve an employee by primary key id.

        Args:
            employee_id: Internal database id.

        Returns:
            Employee if found else None.
        """
        try:
            response = self._execute(
                self.client
                .table(EMPLOYEES_TABLE)
                .select("*")
                .eq("id", employee_id)
                .limit(1)
            )
            if not self._has_data(response):
                return None
            return Employee.model_validate(response.data[0])

        except Exception as exc:
            self.logger.exception("Failed fetching employee by id.")
            raise RepositoryError("Unable to fetch employee.") from exc

    def get_by_employee_no(
        self,
        employee_no: str,
    ) -> Employee | None:
        """
        Retrieve an employee by employee number.

        Args:
            employee_no: Employee identifier.

        Returns:
            Employee if found else None.
        """
        try:
            response = self._execute(
                self.client
                .table(EMPLOYEES_TABLE)
                .select("*")
                .eq("employee_no", employee_no)
                .limit(1)
            )
            if not self._has_data(response):
                return None
            return Employee.model_validate(response.data[0])

        except Exception as exc:
            self.logger.exception("Failed fetching employee.")
            raise RepositoryError("Unable to fetch employee.") from exc

    def get_by_name(
        self,
        name: str,
    ) -> List[Employee]:
        """
        Search employees by name (case-insensitive partial match).

        Args:
            name: Employee name fragment.

        Returns:
            List of matching employees.
        """
        try:
            response = self._execute(
                self.client
                .table(EMPLOYEES_TABLE)
                .select("*")
                .ilike("full_name", f"%{name}%")
            )
            if not self._has_data(response):
                return []
            return [
                Employee.model_validate(row) for row in response.data
            ]

        except Exception as exc:
            self.logger.exception("Employee name search failed.")
            raise RepositoryError("Unable to search employees.") from exc

    def get_all(self) -> List[Employee]:
        """
        Retrieve all employees.

        Returns:
            List of employees.
        """
        try:
            response = self._execute(
                self.client
                .table(EMPLOYEES_TABLE)
                .select("*")
                .order("employee_no")
            )
            if not self._has_data(response):
                return []
            return [
                Employee.model_validate(row) for row in response.data
            ]

        except Exception as exc:
            self.logger.exception("Failed fetching employees.")
            raise RepositoryError("Unable to fetch employees.") from exc

    def search(
        self,
        query: str | None = None,
        is_active: bool | None = None,
        department: str | None = None,
        position_title: str | None = None,
    ) -> List[Employee]:
        """
        Search employees with optional filters.

        Args:
            query: Text search against employee_no or full_name.
            is_active: Filter by active status.
            department: Filter by department name.
            position_title: Filter by position title.

        Returns:
            List of matching employees.
        """
        try:
            q = self.client.table(EMPLOYEES_TABLE).select("*")

            if query:
                q = q.or_(
                    f"employee_no.ilike.%{query}%,"
                    f"full_name.ilike.%{query}%"
                )

            if is_active is not None:
                q = q.eq("is_active", is_active)

            response = self._execute(q.order("employee_no"))

            if not self._has_data(response):
                return []
            return [
                Employee.model_validate(row) for row in response.data
            ]

        except Exception as exc:
            self.logger.exception("Employee search failed.")
            raise RepositoryError("Unable to search employees.") from exc

    def create(self, employee: EmployeeCreate) -> Employee:
        """
        Create a new employee.

        Args:
            employee: Employee creation model.

        Returns:
            Newly created employee.
        """
        try:
            response = self._execute(
                self.client
                .table(EMPLOYEES_TABLE)
                .insert(employee.model_dump())
            )
            if not self._has_data(response):
                raise RepositoryError("Employee creation failed.")

            self.logger.info(
                "Employee %s created successfully.",
                employee.employee_no,
            )
            return Employee.model_validate(response.data[0])

        except Exception as exc:
            self.logger.exception("Failed creating employee.")
            raise RepositoryError("Unable to create employee.") from exc

    def update(
        self,
        employee_no: str,
        employee: EmployeeUpdate | dict[str, Any],
    ) -> Employee:
        """
        Update employee information.

        Args:
            employee_no: Employee identifier.
            employee: Fields to update.

        Returns:
            Updated employee.
        """
        try:
            if isinstance(employee, dict):
                employee = EmployeeUpdate.model_validate(employee)
            values = employee.model_dump(exclude_none=True)
            values["updated_at"] = datetime.utcnow().isoformat()

            response = self._execute(
                self.client
                .table(EMPLOYEES_TABLE)
                .update(values)
                .eq("employee_no", employee_no)
            )
            if not self._has_data(response):
                raise RepositoryError("Employee update failed.")

            self.logger.info("Employee %s updated.", employee_no)
            return Employee.model_validate(response.data[0])

        except Exception as exc:
            self.logger.exception("Failed updating employee.")
            raise RepositoryError("Unable to update employee.") from exc

    def activate(self, employee_no: str) -> Employee:
        """
        Activate an employee.

        Args:
            employee_no: Employee identifier.

        Returns:
            Updated employee.
        """
        return self.update(
            employee_no,
            EmployeeUpdate(is_active=True),
        )

    def deactivate(self, employee_no: str) -> Employee:
        """
        Deactivate an employee.

        Args:
            employee_no: Employee identifier.

        Returns:
            Updated employee.
        """
        return self.update(
            employee_no,
            EmployeeUpdate(is_active=False),
        )

    def delete(self, employee_no: str) -> Employee:
        """
        Soft delete an employee by marking them inactive.

        Args:
            employee_no: Employee identifier.

        Returns:
            Updated employee.
        """
        return self.deactivate(employee_no)

    def get_full_profile(
        self,
        employee_no: str,
    ) -> EmployeeProfileResponse | None:
        """
        Retrieve the complete employee profile across all related tables.

        Joins employees with profiles, contact info, addresses,
        employment details, and the most recent position history entry.

        Args:
            employee_no: Employee identifier.

        Returns:
            Full profile if found else None.
        """
        try:
            joined_select = (
                f"*,"
                f"{EMPLOYEE_PROFILES_TABLE}(*),"
                f"{CONTACT_INFO_TABLE}(*),"
                f"{ADDRESSES_TABLE}(*),"
                f"{EMPLOYMENT_DETAILS_TABLE}(*),"
                f"{POSITION_HISTORY_TABLE}(*)"
            )

            response = self._execute(
                self.client
                .table(EMPLOYEES_TABLE)
                .select(joined_select)
                .eq("employee_no", employee_no)
                .limit(1)
            )
            if not self._has_data(response):
                return None

            row = response.data[0]

            profile_data: dict[str, Any] = {
                "employee_no": row.get("employee_no"),
                "full_name": row.get("full_name"),
                "created_at": row.get("created_at"),
                "is_active": row.get("is_active", True),
            }

            profiles = row.get(EMPLOYEE_PROFILES_TABLE)
            if profiles and len(profiles) > 0:
                p = profiles[0]
                profile_data["dob"] = p.get("dob")
                profile_data["gender"] = p.get("gender")
                profile_data["nationality"] = p.get("nationality")
                profile_data["marital_status"] = p.get("marital_status")
                profile_data["blood_group"] = p.get("blood_group")

            contacts = row.get(CONTACT_INFO_TABLE)
            if contacts and len(contacts) > 0:
                c = contacts[0]
                profile_data["email"] = c.get("email")
                profile_data["phone"] = c.get("phone")

            addresses = row.get(ADDRESSES_TABLE)
            if addresses and len(addresses) > 0:
                a = addresses[0]
                profile_data["city"] = a.get("city")
                profile_data["full_address"] = a.get("full_address")

            employments = row.get(EMPLOYMENT_DETAILS_TABLE)
            if employments and len(employments) > 0:
                e = employments[0]
                profile_data["employment_type"] = e.get("employment_type")
                profile_data["joining_date"] = e.get("joining_date")
                profile_data["status"] = e.get("status")
                profile_data["work_location"] = e.get("work_location")

            positions = row.get(POSITION_HISTORY_TABLE)
            if positions and len(positions) > 0:
                positions_sorted = sorted(
                    positions,
                    key=lambda x: x.get("effective_date", ""),
                    reverse=True,
                )
                latest = positions_sorted[0]
                profile_data["department"] = latest.get("department")
                profile_data["position_title"] = latest.get("position_title")

            return EmployeeProfileResponse.model_validate(profile_data)

        except Exception as exc:
            self.logger.exception(
                "Failed fetching full profile for %s.", employee_no,
            )
            raise RepositoryError("Unable to fetch full profile.") from exc
