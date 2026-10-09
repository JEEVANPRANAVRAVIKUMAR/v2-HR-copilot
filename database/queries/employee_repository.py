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
    DEPARTMENTS_TABLE,
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
            clean_no = str(employee_no).strip()
            response = self._execute(
                self.client
                .table(EMPLOYEES_TABLE)
                .select("*")
                .ilike("employee_no", clean_no)
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
            clean_name = str(name).strip()
            no_space_name = clean_name.replace(" ", "")
            filters = [f"full_name.ilike.%{clean_name}%"]
            if no_space_name != clean_name:
                filters.append(f"full_name.ilike.%{no_space_name}%")
            
            response = self._execute(
                self.client
                .table(EMPLOYEES_TABLE)
                .select("*")
                .or_(",".join(filters))
            )
            if not self._has_data(response):
                # In-memory fallback
                all_res = self._execute(self.client.table(EMPLOYEES_TABLE).select("*"))
                if self._has_data(all_res):
                    return [
                        Employee.model_validate(r) for r in all_res.data
                        if no_space_name.lower() in str(r.get("full_name", "")).replace(" ", "").lower()
                    ]
                return []
            return [
                Employee.model_validate(row) for row in response.data
            ]

        except Exception as exc:
            self.logger.exception("Employee name search failed.")
            raise RepositoryError("Unable to search employees.") from exc

    def get_all(self) -> List[Employee]:
        """
        Retrieve all employees with full joined attributes.

        Returns:
            List of employees with complete credentials, department, and position info.
        """
        return self.search()

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
            select_str = (
                f"*,"
                f"{EMPLOYEE_PROFILES_TABLE}(*),"
                f"{CONTACT_INFO_TABLE}(*),"
                f"{ADDRESSES_TABLE}(*),"
                f"{EMPLOYMENT_DETAILS_TABLE}(*),"
                f"{POSITION_HISTORY_TABLE}(*,{DEPARTMENTS_TABLE}(*))"
            )
            q = self.client.table(EMPLOYEES_TABLE).select(select_str)

            if is_active is not None:
                q = q.eq("is_active", is_active)

            response = self._execute(q.order("employee_no"))

            if not self._has_data(response):
                return []

            results = []
            clean_q = str(query).strip().lower() if query else None
            no_space_q = clean_q.replace(" ", "") if clean_q else None
            q_words = [w for w in clean_q.split() if len(w) > 1] if clean_q else []

            for raw_row in response.data:
                row = dict(raw_row)

                # 1. Contact info
                contacts = row.get(CONTACT_INFO_TABLE) or row.get("contact_info")
                if contacts:
                    c = contacts[0] if isinstance(contacts, list) and len(contacts) > 0 else (contacts if isinstance(contacts, dict) else {})
                    row["email"] = c.get("email")
                    row["phone"] = c.get("phone")

                # 2. Addresses
                addresses = row.get(ADDRESSES_TABLE) or row.get("addresses")
                if addresses:
                    a = addresses[0] if isinstance(addresses, list) and len(addresses) > 0 else (addresses if isinstance(addresses, dict) else {})
                    row["city"] = a.get("city")
                    row["full_address"] = a.get("full_address")

                # 3. Employment details
                dept_name = None
                pos_name = None
                employments = row.get(EMPLOYMENT_DETAILS_TABLE) or row.get("employment_details")
                if employments:
                    e = employments[0] if isinstance(employments, list) and len(employments) > 0 else (employments if isinstance(employments, dict) else {})
                    dept_name = e.get("department")
                    pos_name = e.get("position_title")
                    row["status"] = e.get("status")
                    row["employment_type"] = e.get("employment_type")
                    row["work_location"] = e.get("work_location")
                    row["joining_date"] = e.get("joining_date")

                # 4. Position history (overrides with latest if present)
                pos = row.get(POSITION_HISTORY_TABLE)
                pos_list = [pos] if isinstance(pos, dict) else (pos if isinstance(pos, list) else [])
                if pos_list:
                    sorted_pos = sorted(
                        pos_list,
                        key=lambda x: x.get("start_date", "") or x.get("effective_date", "") or "",
                        reverse=True,
                    )
                    latest = sorted_pos[0]
                    if latest.get("position_title"):
                        pos_name = latest.get("position_title")
                    
                    pos_dept = latest.get("department")
                    if not pos_dept:
                        depts = latest.get("departments") or latest.get(DEPARTMENTS_TABLE)
                        if isinstance(depts, dict):
                            pos_dept = depts.get("department_name")
                        elif isinstance(depts, list) and len(depts) > 0:
                            pos_dept = depts[0].get("department_name")
                    if pos_dept:
                        dept_name = pos_dept

                row["department"] = dept_name
                row["position_title"] = pos_name

                # Filter by text query
                if clean_q:
                    emp_no = str(row.get("employee_no", "")).lower()
                    name = str(row.get("full_name", "")).lower()
                    name_no_space = name.replace(" ", "")

                    matched = (
                        clean_q in emp_no
                        or clean_q in name
                        or (no_space_q and no_space_q in name_no_space)
                        or (q_words and any(w in name for w in q_words))
                    )
                    if not matched:
                        continue

                # Filter by department
                if department:
                    d_filter = str(department).strip().lower()
                    d_val = str(dept_name or "").strip().lower()
                    if d_filter not in d_val and d_val not in d_filter:
                        continue

                # Filter by position_title
                if position_title:
                    p_filter = str(position_title).strip().lower()
                    p_val = str(pos_name or "").strip().lower()
                    if p_filter not in p_val and p_val not in p_filter:
                        continue

                results.append(Employee.model_validate(row))

            return results

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
                f"{POSITION_HISTORY_TABLE}(*,{DEPARTMENTS_TABLE}(*))"
            )

            response = self._execute(
                self.client
                .table(EMPLOYEES_TABLE)
                .select(joined_select)
                .ilike("employee_no", str(employee_no).strip())
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
            if profiles:
                p = profiles[0] if isinstance(profiles, list) and len(profiles) > 0 else (profiles if isinstance(profiles, dict) else None)
                if p:
                    profile_data["dob"] = p.get("dob")
                    profile_data["gender"] = p.get("gender")
                    profile_data["nationality"] = p.get("nationality")
                    profile_data["marital_status"] = p.get("marital_status")
                    profile_data["blood_group"] = p.get("blood_group")

            contacts = row.get(CONTACT_INFO_TABLE)
            if contacts:
                c = contacts[0] if isinstance(contacts, list) and len(contacts) > 0 else (contacts if isinstance(contacts, dict) else None)
                if c:
                    profile_data["email"] = c.get("email")
                    profile_data["phone"] = c.get("phone")

            addresses = row.get(ADDRESSES_TABLE)
            if addresses:
                a = addresses[0] if isinstance(addresses, list) and len(addresses) > 0 else (addresses if isinstance(addresses, dict) else None)
                if a:
                    profile_data["city"] = a.get("city")
                    profile_data["full_address"] = a.get("full_address")

            employments = row.get(EMPLOYMENT_DETAILS_TABLE)
            if employments:
                e = employments[0] if isinstance(employments, list) and len(employments) > 0 else (employments if isinstance(employments, dict) else None)
                if e:
                    profile_data["employment_type"] = e.get("employment_type")
                    profile_data["joining_date"] = e.get("joining_date")
                    profile_data["status"] = e.get("status")
                    profile_data["work_location"] = e.get("work_location")

            positions = row.get(POSITION_HISTORY_TABLE)
            if positions:
                pos_list = [positions] if isinstance(positions, dict) else (positions if isinstance(positions, list) else [])
                if pos_list:
                    positions_sorted = sorted(
                        pos_list,
                        key=lambda x: x.get("start_date", "") or x.get("effective_date", "") or "",
                        reverse=True,
                    )
                    latest = positions_sorted[0]
                    dept_val = latest.get("department")
                    if dept_val is None:
                        depts = latest.get("departments")
                        if isinstance(depts, dict):
                            dept_val = depts.get("department_name")
                        elif isinstance(depts, list) and len(depts) > 0:
                            dept_val = depts[0].get("department_name")
                    profile_data["department"] = dept_val
                    profile_data["position_title"] = latest.get("position_title")

            return EmployeeProfileResponse.model_validate(profile_data)

        except Exception as exc:
            self.logger.exception(
                "Failed fetching full profile for %s.", employee_no,
            )
            raise RepositoryError("Unable to fetch full profile.") from exc

    def upsert_contact_info(
        self, employee_no: str, email: str | None = None, phone: str | None = None,
    ) -> None:
        """Upsert contact details for an employee."""
        try:
            data = {"employee_no": employee_no}
            if email:
                data["email"] = email
            if phone:
                data["phone"] = phone
            if len(data) > 1:
                res = self.client.table(CONTACT_INFO_TABLE).select("*").eq("employee_no", employee_no).execute()
                if self._has_data(res):
                    self.client.table(CONTACT_INFO_TABLE).update(data).eq("employee_no", employee_no).execute()
                else:
                    self.client.table(CONTACT_INFO_TABLE).insert(data).execute()
        except Exception as exc:
            self.logger.warning("Upsert contact_info failed for %s: %s", employee_no, exc)

    def upsert_employment_details(
        self,
        employee_no: str,
        employment_type: str | None = None,
        joining_date: str | None = None,
        status: str | None = None,
        work_location: str | None = None,
    ) -> None:
        """Upsert employment details for an employee."""
        try:
            data = {"employee_no": employee_no}
            if employment_type:
                data["employment_type"] = employment_type
            if joining_date:
                data["joining_date"] = joining_date
            if status:
                data["status"] = status
            if work_location:
                data["work_location"] = work_location
            if len(data) > 1:
                res = self.client.table(EMPLOYMENT_DETAILS_TABLE).select("*").eq("employee_no", employee_no).execute()
                if self._has_data(res):
                    self.client.table(EMPLOYMENT_DETAILS_TABLE).update(data).eq("employee_no", employee_no).execute()
                else:
                    self.client.table(EMPLOYMENT_DETAILS_TABLE).insert(data).execute()
        except Exception as exc:
            self.logger.warning("Upsert employment_details failed for %s: %s", employee_no, exc)

    def upsert_position_history(
        self,
        employee_no: str,
        position_title: str | None = None,
        department_name: str | None = None,
        start_date: str | None = None,
    ) -> None:
        """Upsert position and department assignment for an employee."""
        try:
            dept_id = None
            if department_name:
                d_res = (
                    self.client
                    .table(DEPARTMENTS_TABLE)
                    .select("id")
                    .ilike("department_name", f"%{department_name}%")
                    .limit(1)
                    .execute()
                )
                if self._has_data(d_res):
                    dept_id = d_res.data[0].get("id")

            data = {"employee_no": employee_no}
            if position_title:
                data["position_title"] = position_title
            if dept_id is not None:
                data["department_id"] = dept_id
            if start_date:
                data["start_date"] = start_date
            if len(data) > 1:
                res = self.client.table(POSITION_HISTORY_TABLE).select("*").eq("employee_no", employee_no).execute()
                if self._has_data(res):
                    self.client.table(POSITION_HISTORY_TABLE).update(data).eq("employee_no", employee_no).execute()
                else:
                    self.client.table(POSITION_HISTORY_TABLE).insert(data).execute()
        except Exception as exc:
            self.logger.warning("Upsert position_history failed for %s: %s", employee_no, exc)

    def upsert_address(
        self,
        employee_no: str,
        city: str | None = None,
        full_address: str | None = None,
    ) -> None:
        """Upsert address information for an employee."""
        try:
            data = {"employee_no": employee_no}
            if city:
                data["city"] = city
            if full_address:
                data["full_address"] = full_address
            if len(data) > 1:
                res = self.client.table(ADDRESSES_TABLE).select("*").eq("employee_no", employee_no).execute()
                if self._has_data(res):
                    self.client.table(ADDRESSES_TABLE).update(data).eq("employee_no", employee_no).execute()
                else:
                    self.client.table(ADDRESSES_TABLE).insert(data).execute()
        except Exception as exc:
            self.logger.warning("Upsert addresses failed for %s: %s", employee_no, exc)

    def upsert_profile(
        self,
        employee_no: str,
        dob: str | None = None,
        gender: str | None = None,
        nationality: str | None = None,
        marital_status: str | None = None,
        blood_group: str | None = None,
    ) -> None:
        """Upsert profile metadata for an employee."""
        try:
            data = {"employee_no": employee_no}
            if dob:
                data["dob"] = dob
            if gender:
                data["gender"] = gender
            if nationality:
                data["nationality"] = nationality
            if marital_status:
                data["marital_status"] = marital_status
            if blood_group:
                data["blood_group"] = blood_group
            if len(data) > 1:
                res = self.client.table(EMPLOYEE_PROFILES_TABLE).select("*").eq("employee_no", employee_no).execute()
                if self._has_data(res):
                    self.client.table(EMPLOYEE_PROFILES_TABLE).update(data).eq("employee_no", employee_no).execute()
                else:
                    self.client.table(EMPLOYEE_PROFILES_TABLE).insert(data).execute()
        except Exception as exc:
            self.logger.warning("Upsert employee_profiles failed for %s: %s", employee_no, exc)

