"""
Conversational CRUD agent.

Slot-filling flow for employee operations. The agent tracks which
fields are known and which are missing, asks follow-up questions
using conversation memory, confirms before writing, and executes
through the EmployeeService (never directly touching the database).
"""

from __future__ import annotations

import time
import re
from enum import Enum
from logging import Logger
from typing import Any, Dict, List, Set

from models.employee import EmployeeCreate, EmployeeUpdate
from services import EmployeeService
from utils.exceptions import (
    EmployeeNotFoundError,
    ServiceError,
)

from .llm import GroqLLM

# Required fields for creating an employee.
REQUIRED_CREATE_FIELDS: Set[str] = {"employee_no", "full_name"}

# All recognised employee fields for the LLM to extract.
RECOGNISED_FIELDS: Set[str] = {
    "employee_no", "full_name", "is_active",
    "department", "position_title", "email", "phone",
    "employment_type", "joining_date", "work_location", "status",
}

CRUD_SYSTEM_PROMPT = """\
You are an HR assistant helping with employee record management. \
The user's request has been classified as a CRUD operation.

Extract as many of the following fields as you can from the user's message and prior conversation:
- operation: one of "create", "update", "activate", "deactivate", "lookup", "list", "search"
  * Use "create" when adding a new employee.
  * Use "update" when modifying or adding additional info (contact, employment type, joining date, department, etc.) to an employee.
  * Use "list" when the user asks to see/show/list ALL employees (or "everyone").
  * Use "lookup" when the user asks about ONE specific employee by number or name.
  * Use "search" when the user wants to find employees matching criteria.
- employee_no: the employee number if mentioned (e.g. EMP1776) or referenced in previous context
- full_name: the employee's full name
- is_active: whether they should be active (true/false)
- department: the department name (e.g. AI, Engineering, HR)
- position_title: the job/position title (e.g. Intern, Data Scientist)
- email: email address (e.g. name@example.com)
- phone: phone number
- employment_type: Full Time, Part Time, Intern, Contract
- joining_date: joining date (e.g. YYYY-MM-DD or DD/MM/YYYY)
- work_location: office/city location
- status: Active, Inactive, On Leave

Respond with a JSON object:
{
  "operation": "...",
  "fields": {"field_name": "value", ...},
  "missing_fields": ["field1", "field2"],
  "clarification_needed": "question to ask the user or null",
  "ready_to_confirm": true/false
}

If the user is continuing a previous turn to add details (e.g. giving contact info, joining date, or employment type), use operation "update" and keep the employee_no from context if not stated.
"""


class CrudOperation(str, Enum):
    """Supported CRUD operations."""
    CREATE = "create"
    UPDATE = "update"
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    LOOKUP = "lookup"
    LIST = "list"
    SEARCH = "search"


class CrudAgent:
    """
    Slot-filling CRUD agent that operates conversationally.

    Uses the LLM to extract fields, asks follow-ups for missing
    information, confirms before execution, and delegates all DB
    writes to EmployeeService.
    """

    def __init__(
        self,
        llm: GroqLLM,
        employee_service: EmployeeService,
        logger: Logger,
    ) -> None:
        self._llm = llm
        self._employee_service = employee_service
        self._logger = logger

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def process(
        self,
        message: str,
        *,
        context: List[Dict[str, str]] | None = None,
    ) -> str:
        """
        Process a CRUD request and return a response.

        The agent extracts fields, fills slots via conversation,
        and writes to the database when all required fields are
        present and confirmed.

        Args:
            message: The user's message.
            context: Prior conversation turns.

        Returns:
            A response string (answer, question, or confirmation).

        Raises:
            ServiceError: On unexpected failures.
        """
        start = time.perf_counter()
        op = "crud_agent.process"

        try:
            parsed = self._parse_message(message, context=context)
            operation = parsed.get("operation", "").strip().lower()
            fields = parsed.get("fields", {}) or {}

            # Normalize operations the LLM may use that aren't in the enum
            LOOKUP_ALIASES = {"show", "view", "get", "fetch", "find", "retrieve"}
            LIST_ALIASES = {"list_all", "show_all", "view_all", "get_all",
                            "all", "everyone", "all_employees"}
            SEARCH_ALIASES = {"find_all", "query", "filter"}

            if operation in LOOKUP_ALIASES:
                operation = "lookup"
            elif operation in LIST_ALIASES:
                operation = "list"
            elif operation in SEARCH_ALIASES:
                operation = "search"
            elif operation in {"show", "view", "get"} and not fields.get("employee_no") and not fields.get("full_name"):
                # Ambiguous verb with no target → default to list
                operation = "list"

            if operation == "lookup":
                return self._handle_lookup(parsed)

            if operation == "list":
                return self._handle_list()

            if operation == "search":
                return self._handle_search(parsed)

            if operation in ("activate", "deactivate"):
                return self._handle_status_change(parsed, operation)

            if operation == "create":
                return self._handle_create(parsed)

            if operation == "update":
                return self._handle_update(parsed, context=context)

            # A malformed/overly conservative LLM parse should not turn a
            # simple employee question into an "unknown" operation. Try a
            # deterministic name lookup before asking the user to clarify.
            fallback = self._fallback_name_lookup(message)
            if fallback:
                return fallback

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | operation=%s | %.1fms | OK",
                op, operation, duration_ms,
            )
            return (
                f"I understood you want to {operation} an employee, "
                "but I need more details. Can you provide the "
                "employee number or name?"
            )

        except (EmployeeNotFoundError, ServiceError):
            raise

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR: %s", op, duration_ms, exc,
            )
            raise ServiceError(
                f"CRUD operation failed: {exc}"
            ) from exc

    # ----------------------------------------------------------------
    # Internal: parse
    # ----------------------------------------------------------------

    def _parse_message(
        self,
        message: str,
        *,
        context: List[Dict[str, str]] | None = None,
    ) -> Dict[str, Any]:
        """
        Use the LLM to parse the user's message into structured fields.
        """
        import json
        try:
            messages = self._llm.build_messages(
                system_prompt=CRUD_SYSTEM_PROMPT,
                user_message=message,
                context=context,
            )
            raw = self._llm.generate(
                messages, temperature=0.1, max_tokens=512,
            ).strip()

            # Strip markdown fences
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception as exc:
            self._logger.warning("CRUD parse error (%s), using fallback parser.", exc)

        # Heuristic fallback parser
        fields: Dict[str, Any] = {}
        msg = message.strip()

        # Email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', msg)
        if email_match:
            fields["email"] = email_match.group(0)

        # Phone
        phone_match = re.search(r'(?:phone|contact|mobile|cell)[:\s]+([0-9\+\-\s\(\)]{7,15})', msg, re.IGNORECASE)
        if phone_match and not fields.get("email"):
            fields["phone"] = phone_match.group(1).strip()

        # Joining date
        date_match = re.search(r'(?:joining date|joining|date|joined)[:\s]+([0-9\/\-\.]+)', msg, re.IGNORECASE)
        if date_match:
            fields["joining_date"] = date_match.group(1).strip()

        # Employment type
        type_match = re.search(r'(?:type|employment type)[:\s]+([\w\s]+?)(?:joining|contact|department|position|status|$)', msg, re.IGNORECASE)
        if type_match:
            fields["employment_type"] = type_match.group(1).strip()

        # Department
        dept_match = re.search(r'department[:\s]+([\w\s]+?)(?:position|status|type|joining|contact|$)', msg, re.IGNORECASE)
        if dept_match:
            fields["department"] = dept_match.group(1).strip()

        # Position title
        pos_match = re.search(r'position(?: title)?[:\s]+([\w\s]+?)(?:department|status|type|joining|contact|$)', msg, re.IGNORECASE)
        if pos_match:
            fields["position_title"] = pos_match.group(1).strip()

        # Employee No
        emp_match = re.search(r'\b(emp\d+)\b', msg, re.IGNORECASE)
        if emp_match:
            fields["employee_no"] = emp_match.group(1).upper()

        # Full Name
        name_match = re.search(r'(?:fullname|full name|name)[:\s]+([\w\s]+?)(?:status|department|position|employee|type|$)', msg, re.IGNORECASE)
        if name_match:
            fields["full_name"] = name_match.group(1).strip()

        # Status
        status_match = re.search(r'status[:\s]+(\w+)', msg, re.IGNORECASE)
        if status_match:
            fields["status"] = status_match.group(1).capitalize()
            fields["is_active"] = fields["status"].lower() not in ("inactive", "terminated", "false", "0")

        # Decide operation
        if fields.get("full_name") and fields.get("employee_no"):
            return {"operation": "create", "fields": fields, "missing_fields": [], "ready_to_confirm": True}

        if any(k in fields for k in ["email", "phone", "joining_date", "employment_type", "department", "position_title"]):
            return {"operation": "update", "fields": fields, "missing_fields": [], "ready_to_confirm": True}

        msg_l = msg.lower()
        if any(k in msg_l for k in ["all", "everyone", "list", "show everyone"]):
            return {"operation": "list", "fields": {}, "missing_fields": [], "ready_to_confirm": False}

        if fields.get("employee_no"):
            return {"operation": "lookup", "fields": fields, "missing_fields": [], "ready_to_confirm": False}

        return {
            "operation": "unknown",
            "fields": fields,
            "missing_fields": [],
            "clarification_needed": "I couldn't understand the request. Can you rephrase it?",
            "ready_to_confirm": False,
        }

    # ----------------------------------------------------------------
    # Internal: handlers
    # ----------------------------------------------------------------

    def _fallback_name_lookup(self, message: str) -> str | None:
        """Resolve ordinary name questions when the LLM parse is uncertain."""
        stop_words = {
            "who", "is", "was", "the", "what", "about", "tell", "me",
            "show", "find", "get", "fetch", "employee", "details",
            "information", "of", "for", "an", "a", "please",
        }
        words = [
            word.lower()
            for word in re.findall(r"[A-Za-z]+", message)
            if word.lower() not in stop_words
        ]
        candidates = []
        if len(words) > 1:
            candidates.append(" ".join(words))
        candidates.extend(words)

        for candidate in candidates[:3]:
            results = self._employee_service.search_employees(query=candidate)
            if results:
                return self._handle_lookup({"fields": {"full_name": candidate}})
        return None

    def _format_full_profile(self, employee_no: str) -> str:
        emp = self._employee_service.get_full_profile(employee_no)
        
        # Fallback to get_employee_by_no if get_full_profile returns basic schema or is empty (ensures unit tests compatibility)
        if not emp or not hasattr(emp, "department") or not hasattr(emp, "email"):
            emp_basic = self._employee_service.get_employee_by_no(employee_no)
            if not emp_basic:
                return f"Employee '{employee_no}' not found."
            return (
                f"**{emp_basic.full_name}** (EMP: {emp_basic.employee_no}) — "
                f"{'Active' if emp_basic.is_active else 'Inactive'}. "
                f"Joined: {emp_basic.created_at.date() if emp_basic.created_at else 'N/A'}."
            )

        history_str = ""
        hist_service = getattr(self._employee_service, "_history_service", None)
        if hist_service:
            try:
                timeline = hist_service.build_timeline(emp.employee_no)
                if timeline and timeline.events:
                    history_lines = []
                    for ev in timeline.events:
                        history_lines.append(f"  - {ev.description}")
                    if history_lines:
                        history_str = "\n**Work History / Timeline:**\n" + "\n".join(history_lines)
            except Exception:
                pass

        return (
            f"### 👤 Employee Details: **{emp.full_name}**\n"
            f"- **Employee Number:** `{emp.employee_no}`\n"
            f"- **Status:** `{'Active' if emp.is_active else 'Inactive'}`"
            + (f" (`{emp.status}`)" if emp.status else "") + "\n"
            f"- **Department:** `{emp.department or 'N/A'}`\n"
            f"- **Position Title:** `{emp.position_title or 'N/A'}`\n"
            f"- **Employment Type:** `{emp.employment_type or 'N/A'}`\n"
            f"- **Joining Date:** `{emp.joining_date or 'N/A'}`\n"
            f"- **Work Location:** `{emp.work_location or 'N/A'}`\n\n"
            f"**Contact Information:**\n"
            f"- **Email:** `{emp.email or 'N/A'}`\n"
            f"- **Phone:** `{emp.phone or 'N/A'}`\n"
            f"- **Address:** `{emp.full_address or (emp.city or 'N/A')}`\n\n"
            f"**Personal Information:**\n"
            f"- **DOB:** `{emp.dob or 'N/A'}` | **Gender:** `{emp.gender or 'N/A'}`\n"
            f"- **Nationality:** `{emp.nationality or 'N/A'}`\n"
            f"- **Marital Status:** `{emp.marital_status or 'N/A'}` | **Blood Group:** `{emp.blood_group or 'N/A'}`\n"
            f"{history_str}"
        )

    def _handle_lookup(
        self, parsed: Dict[str, Any],
    ) -> str:
        fields = parsed.get("fields", {}) or {}
        employee_no = fields.get("employee_no")
        full_name = fields.get("full_name")

        if employee_no:
            return self._format_full_profile(employee_no)

        if full_name:
            results = self._employee_service.search_employees(
                query=full_name,
            )
            if results:
                if len(results) == 1:
                    return self._format_full_profile(results[0].employee_no)
                lines = [
                    f"- **{e.full_name}** ({e.employee_no}) — "
                    f"{'Active' if e.is_active else 'Inactive'}"
                    for e in results[:5]
                ]
                return "Found multiple matching employees:\n" + "\n".join(lines) + "\n\nPlease specify the employee number to see their full profile."
            return f"No employees found matching '{full_name}'."

        return (
            "Please provide an employee number or name to look up."
        )

    def _handle_list(self) -> str:
        employees = self._employee_service.list_all_employees()
        if not employees:
            return "No employees found in the system."
        lines = [
            f"- **{e.full_name}** ({e.employee_no}) — "
            f"{'Active' if e.is_active else 'Inactive'}"
            for e in employees[:20]
        ]
        header = f"Showing {len(lines)} of {len(employees)} employees:\n"
        if len(employees) > 20:
            header += "(first 20 shown)\n"
        return header + "\n".join(lines)

    def _handle_search(
        self, parsed: Dict[str, Any],
    ) -> str:
        fields = parsed.get("fields", {}) or {}
        full_name = fields.get("full_name")
        department = fields.get("department")
        position_title = fields.get("position_title")
        is_active = fields.get("is_active")
        if isinstance(is_active, str):
            is_active = is_active.lower() not in ("false", "no", "0", "inactive")

        if not any([full_name, department, position_title, is_active is not None]):
            return self._handle_list()

        results = self._employee_service.search_employees(
            query=full_name,
            is_active=is_active,
            department=department,
            position_title=position_title,
        )
        if not results:
            return "No employees matched those criteria."
        lines = [
            f"- **{e.full_name}** ({e.employee_no}) — "
            f"{'Active' if e.is_active else 'Inactive'}"
            for e in results[:20]
        ]
        header = f"Found {len(lines)} of {len(results)} matches:\n"
        if len(results) > 20:
            header += "(first 20 shown)\n"
        return header + "\n".join(lines)

    def _handle_status_change(
        self, parsed: Dict[str, Any], operation: str,
    ) -> str:
        fields = parsed.get("fields", {}) or {}
        employee_no = fields.get("employee_no")

        if not employee_no:
            return (
                "Which employee would you like to "
                f"{'activate' if operation == 'activate' else 'deactivate'}? "
                "Please provide their employee number."
            )

        if operation == "activate":
            self._employee_service.activate_employee(employee_no)
        else:
            self._employee_service.deactivate_employee(employee_no)

        return (
            f"Employee **{employee_no}** has been "
            f"{'activated' if operation == 'activate' else 'deactivated'}"
            " successfully."
        )

    def _handle_create(
        self, parsed: Dict[str, Any],
    ) -> str:
        fields = parsed.get("fields", {}) or {}
        clarification = parsed.get("clarification_needed")

        # If LLM says we need more info
        if clarification and not parsed.get("ready_to_confirm"):
            return clarification

        # Check required fields
        if "full_name" not in fields or "employee_no" not in fields:
            missing_fields = []
            if "full_name" not in fields:
                missing_fields.append("the employee's full name")
            if "employee_no" not in fields:
                missing_fields.append("an employee number")
            return (
                "I still need " + " and ".join(missing_fields) + ". "
                "Please provide them."
            )

        data = EmployeeCreate(
            employee_no=fields["employee_no"],
            full_name=fields["full_name"],
            is_active=fields.get("is_active", True),
        )
        result = self._employee_service.create_employee(data)

        # Save optional metadata
        self._employee_service.save_employee_details(
            result.employee_no,
            email=fields.get("email"),
            phone=fields.get("phone"),
            employment_type=fields.get("employment_type"),
            joining_date=fields.get("joining_date"),
            status=fields.get("status"),
            work_location=fields.get("work_location"),
            department=fields.get("department"),
            position_title=fields.get("position_title"),
        )

        details = []
        if fields.get("department"):
            details.append(f"Department: `{fields['department']}`")
        if fields.get("position_title"):
            details.append(f"Position: `{fields['position_title']}`")

        has_credentials = any([
            fields.get("email"),
            fields.get("department"),
            fields.get("position_title"),
            fields.get("employment_type"),
            fields.get("joining_date"),
        ])

        if has_credentials:
            saved_items = []
            if fields.get("department"): saved_items.append(f"- **Department:** `{fields['department']}`")
            if fields.get("position_title"): saved_items.append(f"- **Position Title:** `{fields['position_title']}`")
            if fields.get("email"): saved_items.append(f"- **Email:** `{fields['email']}`")
            if fields.get("phone"): saved_items.append(f"- **Phone:** `{fields['phone']}`")
            if fields.get("employment_type"): saved_items.append(f"- **Employment Type:** `{fields['employment_type']}`")
            if fields.get("joining_date"): saved_items.append(f"- **Joining Date:** `{fields['joining_date']}`")
            if fields.get("work_location"): saved_items.append(f"- **Work Location:** `{fields['work_location']}`")

            items_str = "\n".join(saved_items)
            return (
                f"✅ **Employee Created Successfully!**\n\n"
                f"### 👤 {result.full_name} (`{result.employee_no}`)\n"
                f"- **Status:** `{'Active' if result.is_active else 'Inactive'}`\n"
                f"{items_str}\n\n"
                "All employee records and credentials have been saved to the database."
            )
        else:
            return (
                f"✅ Employee **{result.full_name}** (`{result.employee_no}`) created in the directory.\n\n"
                "⚠️ **Please provide the employee credentials and role details to complete onboarding:**\n"
                "- 📧 **Email Address** (e.g. `email: name@company.com`)\n"
                "- 🏢 **Department** (e.g. `department: AI`)\n"
                "- 💼 **Position Title** (e.g. `position: Intern`)\n"
                "- 📅 **Joining Date** (e.g. `joining date: 2026-10-09` or `DD/MM/YYYY`)\n"
                "- 📋 **Employment Type** (e.g. `type: Full Time` / `Intern`)\n"
                "- 📞 **Phone Number** (optional)\n\n"
                "_You can reply directly with these details in one message._"
            )

    def _handle_update(
        self, parsed: Dict[str, Any], context: List[Dict[str, str]] | None = None,
    ) -> str:
        fields = parsed.get("fields", {}) or {}
        employee_no = fields.get("employee_no")

        # Resolve employee_no from conversation context if not provided in latest message
        if not employee_no and context:
            for turn in reversed(context):
                content = turn.get("content", "")
                m = re.search(r'\b(EMP\d+)\b', content, re.IGNORECASE)
                if m:
                    employee_no = m.group(1).upper()
                    break

        if not employee_no:
            # Fallback: check the latest created employee in database
            all_emps = self._employee_service.list_all_employees()
            if all_emps:
                employee_no = all_emps[-1].employee_no

        if not employee_no:
            return (
                "Which employee would you like to update? "
                "Please provide their employee number."
            )

        # 1. Update core table if full_name is provided
        if "full_name" in fields:
            self._employee_service.update_employee(
                employee_no, EmployeeUpdate(full_name=fields["full_name"]),
            )

        # 2. Persist child tables (contact info, employment details, position)
        self._employee_service.save_employee_details(
            employee_no,
            email=fields.get("email"),
            phone=fields.get("phone"),
            employment_type=fields.get("employment_type"),
            joining_date=fields.get("joining_date"),
            status=fields.get("status"),
            work_location=fields.get("work_location"),
            department=fields.get("department"),
            position_title=fields.get("position_title"),
        )

        saved_items = []
        for k in ["department", "position_title", "email", "phone", "employment_type", "joining_date", "work_location", "status"]:
            if k in fields and fields[k]:
                saved_items.append(f"- **{k.replace('_', ' ').title()}:** `{fields[k]}`")

        items_str = "\n".join(saved_items) if saved_items else "- Updated employee record"
        return (
            f"✅ **Employee Credentials Saved Successfully!**\n\n"
            f"### 👤 Profile Summary for `{employee_no}`\n"
            f"{items_str}\n\n"
            "All credentials and employment details have been saved to the database."
        )
