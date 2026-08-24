"""
SQL query repository.

Provides read-only SQL execution through Supabase REST API.
Every query is validated before execution to block destructive
statements. Because no raw SQL RPC exists, SELECT queries are
translated to Supabase client builder calls where possible,
and complex aggregations are handled in Python.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from core.constants import (
    ADDRESSES_TABLE,
    CONTACT_INFO_TABLE,
    DEPARTMENTS_TABLE,
    EMPLOYEES_TABLE,
    EMPLOYMENT_DETAILS_TABLE,
    EMPLOYEE_EMBEDDINGS_TABLE,
    EMPLOYEE_INGESTION_LOGS_TABLE,
    EMPLOYEE_PROFILES_TABLE,
    EMERGENCY_CONTACTS_TABLE,
    POSITION_HISTORY_TABLE,
    EMPLOYEE_HISTORY_TABLE,
)
from database.queries.base_repository import BaseRepository
from utils.exceptions import RepositoryError, SqlGenerationError

ALLOWED_TABLES = frozenset({
    EMPLOYEES_TABLE,
    EMPLOYEE_PROFILES_TABLE,
    CONTACT_INFO_TABLE,
    ADDRESSES_TABLE,
    EMPLOYMENT_DETAILS_TABLE,
    POSITION_HISTORY_TABLE,
    DEPARTMENTS_TABLE,
    EMPLOYEE_EMBEDDINGS_TABLE,
    EMPLOYEE_INGESTION_LOGS_TABLE,
    EMERGENCY_CONTACTS_TABLE,
    EMPLOYEE_HISTORY_TABLE,
})

_SELECT_ONLY_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_DESTRUCTIVE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE"
    r"|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)
_COMMENT_RE = re.compile(r"--.*$|/\*.*?\*/", re.DOTALL | re.MULTILINE)

# Supabase table mapping for FROM clause detection
# These are the actual Supabase table names the REST API uses
_TABLE_MAP = {
    "employees": EMPLOYEES_TABLE,
    "employee_profiles": EMPLOYEE_PROFILES_TABLE,
    "contact_info": CONTACT_INFO_TABLE,
    "addresses": ADDRESSES_TABLE,
    "employment_details": EMPLOYMENT_DETAILS_TABLE,
    "position_history": POSITION_HISTORY_TABLE,
    "departments": DEPARTMENTS_TABLE,
    "employee_embeddings": EMPLOYEE_EMBEDDINGS_TABLE,
    "employee_ingestion_logs": EMPLOYEE_INGESTION_LOGS_TABLE,
    "emergency_contacts": EMERGENCY_CONTACTS_TABLE,
    "employee_history": EMPLOYEE_HISTORY_TABLE,
}


class SqlQueryRepository(BaseRepository):
    """
    Repository for executing validated read-only SQL queries
    via Supabase REST API (no raw SQL RPC available).
    """

    def execute(self, sql: str) -> List[Dict[str, Any]]:
        """
        Validate and execute a read-only SQL query.

        Translates simple SELECT patterns to Supabase builder
        calls where possible; falls back to Python-side
        aggregation for complex queries.
        """
        self._validate_sql(sql)

        self.logger.info("Executing validated SQL via Supabase REST.")

        try:
            # Prefer the project's read-only SQL RPC when it is available.
            # The REST translation remains the fallback for installations
            # where that function has not been deployed.
            rpc_response = self.client.rpc(
                "execute_sql", {"query": sql}
            ).execute()
            rpc_data = getattr(rpc_response, "data", None)
            if isinstance(rpc_data, list):
                self.logger.info(
                    "SQL query returned %d row(s).", len(rpc_data)
                )
                return rpc_data
        except Exception:
            pass

        try:
            # Try translation to Supabase native query
            data = self._execute_translated(sql)
            self.logger.info("SQL query returned %d row(s).", len(data))
            return data
        except Exception as exc:
            self.logger.exception("SQL execution via REST failed.")
            raise RepositoryError("SQL execution failed.") from exc

    def list_tables(self) -> List[str]:
        return sorted(ALLOWED_TABLES)

    def get_table_schema_hint(self) -> str:
        return """Available tables and columns:
- employees (employee_no TEXT PK, full_name TEXT, is_active BOOLEAN)
- employee_profiles (employee_no TEXT FK, dob DATE, gender TEXT, nationality TEXT, marital_status TEXT, blood_group TEXT)
- contact_info (employee_no TEXT FK, email TEXT, phone TEXT)
- addresses (employee_no TEXT FK, city TEXT, full_address TEXT)
- employment_details (employee_no TEXT FK, employment_type TEXT, status TEXT, joining_date DATE, work_location TEXT)
- position_history (employee_no TEXT FK, position_title TEXT, department_id INTEGER FK, start_date DATE, end_date DATE, salary NUMERIC)
- departments (id INTEGER PK, department_name TEXT)

Query Rules:
1. To query an employee's department, JOIN position_history on employee_no, and departments on department_id = departments.id, then filter or group by departments.department_name.
2. To query an employee's position title, use position_history.position_title. Never select employees.job_title or employees.position_title directly as they do not exist.
3. Filter active status using employees.is_active = true.
"""

    # ----------------------------------------------------------------
    # Translation engine
    # ----------------------------------------------------------------

    def _flatten_employee_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten nested table structures in an employee row to root keys."""
        flat = dict(row)
        
        # 1. Profiles
        profiles = row.get(EMPLOYEE_PROFILES_TABLE) or row.get("employee_profiles")
        if profiles:
            p = profiles[0] if isinstance(profiles, list) and len(profiles) > 0 else (profiles if isinstance(profiles, dict) else {})
            for k, v in p.items():
                if k not in flat:
                    flat[k] = v

        # 2. Contact Info
        contacts = row.get(CONTACT_INFO_TABLE) or row.get("contact_info")
        if contacts:
            c = contacts[0] if isinstance(contacts, list) and len(contacts) > 0 else (contacts if isinstance(contacts, dict) else {})
            for k, v in c.items():
                if k not in flat:
                    flat[k] = v

        # 3. Addresses
        addresses = row.get(ADDRESSES_TABLE) or row.get("addresses")
        if addresses:
            a = addresses[0] if isinstance(addresses, list) and len(addresses) > 0 else (addresses if isinstance(addresses, dict) else {})
            for k, v in a.items():
                if k not in flat:
                    flat[k] = v

        # 4. Employment Details
        employments = row.get(EMPLOYMENT_DETAILS_TABLE) or row.get("employment_details")
        if employments:
            e = employments[0] if isinstance(employments, list) and len(employments) > 0 else (employments if isinstance(employments, dict) else {})
            for k, v in e.items():
                if k not in flat:
                    flat[k] = v

        # 5. Position History & Departments
        positions = row.get(POSITION_HISTORY_TABLE) or row.get("position_history")
        if positions:
            pos_list = [positions] if isinstance(positions, dict) else (positions if isinstance(positions, list) else [])
            if pos_list:
                # Sort to get the latest position title/department
                pos_sorted = sorted(
                    pos_list,
                    key=lambda x: x.get("effective_date", x.get("start_date", "") or ""),
                    reverse=True,
                )
                latest = pos_sorted[0]
                for k, v in latest.items():
                    if k not in flat:
                        flat[k] = v
                
                # Extract department name
                dept_val = latest.get("department")
                if dept_val is None:
                    depts = latest.get("departments") or latest.get(DEPARTMENTS_TABLE)
                    if isinstance(depts, dict):
                        dept_val = depts.get("department_name")
                    elif isinstance(depts, list) and len(depts) > 0:
                        dept_val = depts[0].get("department_name")
                if dept_val:
                    flat["department_name"] = dept_val
                    flat["department"] = dept_val

        return flat

    def _execute_translated(self, sql: str) -> List[Dict[str, Any]]:
        """
        Translate a validated SELECT to Supabase REST calls.
        """
        cleaned = _COMMENT_RE.sub("", sql).strip()

        # Detect the primary table
        from_match = re.search(r"FROM\s+(\w+)", cleaned, re.IGNORECASE)
        if not from_match:
            raise RepositoryError("Cannot determine primary table from SQL.")
        table_alias = from_match.group(1).lower()
        table_name = _TABLE_MAP.get(table_alias, table_alias)

        # Build a selective fetch
        try:
            if table_name == EMPLOYEES_TABLE:
                # Fetch full join to support joins in memory
                joined_select = (
                    f"*,"
                    f"{EMPLOYEE_PROFILES_TABLE}(*),"
                    f"{CONTACT_INFO_TABLE}(*),"
                    f"{ADDRESSES_TABLE}(*),"
                    f"{EMPLOYMENT_DETAILS_TABLE}(*),"
                    f"{POSITION_HISTORY_TABLE}(*,{DEPARTMENTS_TABLE}(*))"
                )
                response = self._execute(
                    self.client.table(EMPLOYEES_TABLE).select(joined_select)
                )
                raw_rows = response.data if self._has_data(response) else []
                rows = [self._flatten_employee_row(r) for r in raw_rows]
            else:
                response = self._execute(
                    self.client.table(table_name).select("*")
                )
                rows = response.data if self._has_data(response) else []
        except Exception:
            rows = []

        # Apply post-fetch filtering and aggregation
        rows = self._post_filter(cleaned, rows, table_name)
        rows = self._post_aggregate(cleaned, rows)

        # ORDER BY / LIMIT
        rows = self._apply_order_limit(cleaned, rows)

        return rows

    def _fetch_with_filters(
        self, sql: str, table_name: str, joins: list,
    ) -> List[Dict[str, Any]]:
        """
        Dummy fetch with filters wrapper (not used when using full fetch translation).
        """
        response = self._execute(self.client.table(table_name).select("*"))
        return response.data if self._has_data(response) else []

    def _post_filter(
        self, sql: str, rows: List[Dict[str, Any]], table_name: str,
    ) -> List[Dict[str, Any]]:
        """
        Apply WHERE-style filters in Python on already-fetched rows.
        """
        if not rows:
            return rows

        where_clause = re.search(r"WHERE\s+(.+?)(?:GROUP\s+BY|ORDER\s+BY|LIMIT|;$)", sql, re.IGNORECASE | re.DOTALL)
        if not where_clause:
            return rows

        where_text = where_clause.group(1).strip().rstrip(";").rstrip(")").strip()

        filtered = rows
        
        # 1. Parse simple equals (=) conditions safely
        for eq_match in re.finditer(
            r"(\w+)\.(\w+)\s*=\s*(?:['\"]([^'\"]+)['\"]|([^\s'\")]+))",
            where_text, re.IGNORECASE,
        ):
            column = eq_match.group(2).lower()
            value = (eq_match.group(3) or eq_match.group(4) or "").strip()

            # Handle boolean true/false
            if value.lower() == "true":
                filtered = [r for r in filtered if r.get(column) in (True, "true", "True")]
            elif value.lower() == "false":
                filtered = [r for r in filtered if r.get(column) in (False, "false", "False")]
            else:
                filtered = [r for r in filtered if str(r.get(column, "")) == value]

        # 2. Parse ILIKE conditions safely
        for ilike_match in re.finditer(
            r"(\w+)\.(\w+)\s+ILIKE\s+['\"]%?([^%'\"]+)%?['\"]",
            where_text, re.IGNORECASE,
        ):
            column = ilike_match.group(2).lower()
            val = ilike_match.group(3).strip().lower()
            filtered = [r for r in filtered if val in str(r.get(column, "")).lower()]

        # 3. Parse comparisons (>, <, >=, <=) safely
        for comp_match in re.finditer(
            r"(\w+)\.(\w+)\s*(>=|<=|>|<)\s*([0-9.]+)",
            where_text, re.IGNORECASE,
        ):
            column = comp_match.group(2).lower()
            op = comp_match.group(3)
            val = float(comp_match.group(4))
            
            def compare(row_val, operator, limit):
                try:
                    num = float(row_val)
                    if operator == ">": return num > limit
                    if operator == "<": return num < limit
                    if operator == ">=": return num >= limit
                    if operator == "<=": return num <= limit
                except (ValueError, TypeError):
                    return False
            
            filtered = [r for r in filtered if compare(r.get(column), op, val)]

        # 4. Parse IS NOT NULL conditions
        for ne_match in re.finditer(
            r"(\w+)\.(\w+)\s*(?:IS\s+NOT|!=|<>)\s*(?:NULL|null)",
            where_text, re.IGNORECASE,
        ):
            column = ne_match.group(2).lower()
            filtered = [r for r in filtered if r.get(column) is not None]

        return filtered

    def _post_aggregate(
        self, sql: str, rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Handle GROUP BY + COUNT in Python.
        """
        group_match = re.search(
            r"GROUP\s+BY\s+(.+?)(?:ORDER\s+BY|LIMIT|;$)",
            sql, re.IGNORECASE | re.DOTALL,
        )
        if not group_match:
            return rows

        group_cols = group_match.group(1).strip().rstrip(";")
        cols = [c.strip().split(".")[-1] for c in group_cols.split(",")]

        # Check for COUNT aggregation
        has_count = bool(re.search(r"COUNT\s*\(\s*\*?\s*\)", sql, re.IGNORECASE))
        has_count_distinct = bool(re.search(r"COUNT\s*\(\s*DISTINCT\s+", sql, re.IGNORECASE))

        if has_count or has_count_distinct:
            result = []
            groups: dict[tuple, set] = {}
            for row in rows:
                key = tuple(str(row.get(c, "")) for c in cols)
                if key not in groups:
                    groups[key] = set()
                groups[key].add(row.get("employee_no", str(row)))

            for key, emps in groups.items():
                entry = {"count": len(emps)}
                for i, c in enumerate(cols):
                    entry[c] = key[i] if len(key) > i else key[0]
                result.append(entry)

            # Sort by count DESC
            result.sort(key=lambda r: r.get("count", 0), reverse=True)
            return result

        return rows

    def _apply_order_limit(
        self, sql: str, rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Apply ORDER BY and LIMIT in Python.
        """
        order_match = re.search(
            r"ORDER\s+BY\s+(\w+(?:\.\w+)?)\s*(DESC|ASC)?",
            sql, re.IGNORECASE,
        )
        if order_match and rows:
            col = order_match.group(1).split(".")[-1]
            reverse = order_match.group(2).upper() == "DESC" if order_match.group(2) else False
            try:
                rows = sorted(rows, key=lambda r: r.get(col) or "", reverse=reverse)
            except Exception:
                pass

        limit_match = re.search(r"LIMIT\s+(\d+)", sql, re.IGNORECASE)
        if limit_match and rows:
            limit = int(limit_match.group(1))
            rows = rows[:limit]

        return rows

    # ----------------------------------------------------------------
    # Validation (unchanged from original)
    # ----------------------------------------------------------------

    @classmethod
    def _validate_sql(cls, sql: str) -> None:
        stripped = sql.strip()
        if not stripped:
            raise SqlGenerationError("Empty SQL query.")
        no_comments = _COMMENT_RE.sub("", stripped)
        if _DESTRUCTIVE_RE.search(no_comments):
            raise SqlGenerationError("Destructive SQL statements are not allowed.")
        if not _SELECT_ONLY_RE.search(no_comments):
            raise SqlGenerationError("Only SELECT queries are allowed.")
        cls._validate_tables(no_comments)

    @classmethod
    def _validate_tables(cls, sql: str) -> None:
        refs = set()
        for match in re.finditer(r"\b(?:FROM|JOIN)\s+(\w+)", sql, re.IGNORECASE):
            refs.add(match.group(1).lower())
        for ref in refs:
            if ref not in {t.lower() for t in ALLOWED_TABLES}:
                raise SqlGenerationError(f"Table '{ref}' is not in the allowed set.")
