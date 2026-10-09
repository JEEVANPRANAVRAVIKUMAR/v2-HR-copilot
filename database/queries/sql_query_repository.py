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

        # Detect all referenced tables
        all_refs = [t.lower() for t in re.findall(r"\b(?:FROM|JOIN)\s+(\w+)", cleaned, re.IGNORECASE)]
        
        # Determine if we should query the rich joined employee dataset
        employee_related = {
            "employees", "employee_profiles", "contact_info", "addresses",
            "employment_details", "position_history",
        }
        
        should_fetch_employees = (
            any(t in employee_related for t in all_refs)
            or len(all_refs) > 1
            or "employee_no" in cleaned.lower()
            or "full_name" in cleaned.lower()
            or "position_title" in cleaned.lower()
            or "city" in cleaned.lower()
        )

        try:
            if should_fetch_employees:
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
                table_name = EMPLOYEES_TABLE
            else:
                from_match = re.search(r"FROM\s+(\w+)", cleaned, re.IGNORECASE)
                table_alias = from_match.group(1).lower() if from_match else "departments"
                table_name = _TABLE_MAP.get(table_alias, table_alias)
                response = self._execute(
                    self.client.table(table_name).select("*")
                )
                rows = response.data if self._has_data(response) else []
        except Exception as exc:
            self.logger.warning("Supabase table query fallback encountered error: %s", exc)
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

        def _get_val(row_dict: dict, col: str):
            col_l = col.lower()
            if col_l in row_dict:
                return row_dict[col_l]
            # Try matching without prefixes or alias
            for k, v in row_dict.items():
                if k.lower() == col_l or k.lower().endswith(f"_{col_l}"):
                    return v
            return None

        # 1. Parse simple equals (=) conditions (e.g. d.department_name = 'AI' or is_active = true)
        for eq_match in re.finditer(
            r"(?:(\w+)\.)?(\w+)\s*=\s*(?:['\"]([^'\"]+)['\"]|([^\s'\")]+))",
            where_text, re.IGNORECASE,
        ):
            column = eq_match.group(2).lower()
            val_quoted = eq_match.group(3)
            val_unquoted = eq_match.group(4)
            value = (val_quoted or val_unquoted or "").strip()

            # If unquoted value looks like a column/table join reference (e.g. d.id, position_history.employee_no), skip it
            if val_unquoted and ("." in val_unquoted or val_unquoted.lower() in ("id", "employee_no", "department_id")):
                continue

            if value.lower() in ("true", "false"):
                target_bool = value.lower() == "true"
                filtered = [r for r in filtered if bool(_get_val(r, column)) == target_bool]
            else:
                filtered = [
                    r for r in filtered
                    if str(_get_val(r, column) or "").strip().lower() == value.lower()
                ]

        # 2. Parse ILIKE / LIKE conditions (e.g. ph.position_title ILIKE '%Manager%')
        for like_match in re.finditer(
            r"(?:(\w+)\.)?(\w+)\s+(?:ILIKE|LIKE)\s+['\"]%?([^%'\"]+)%?['\"]",
            where_text, re.IGNORECASE,
        ):
            column = like_match.group(2).lower()
            val = like_match.group(3).strip().lower()
            filtered = [
                r for r in filtered
                if val in str(_get_val(r, column) or "").lower()
            ]

        # 3. Parse IN conditions (e.g. d.department_name IN ('AI', 'Engineering'))
        for in_match in re.finditer(
            r"(?:(\w+)\.)?(\w+)\s+IN\s*\(([^)]+)\)",
            where_text, re.IGNORECASE,
        ):
            column = in_match.group(2).lower()
            in_vals = [
                v.strip().strip("'\"").lower()
                for v in in_match.group(3).split(",")
            ]
            filtered = [
                r for r in filtered
                if str(_get_val(r, column) or "").strip().lower() in in_vals
            ]

        # 4. Parse BETWEEN conditions (e.g. joining_date BETWEEN '2022-01-01' AND '2023-12-31')
        for bet_match in re.finditer(
            r"(?:(\w+)\.)?(\w+)\s+BETWEEN\s+['\"]?([^'\"]+?)['\"]?\s+AND\s+['\"]?([^'\"]+?)['\"]?(?:\s|$)",
            where_text, re.IGNORECASE,
        ):
            column = bet_match.group(2).lower()
            start_v = bet_match.group(3).strip()
            end_v = bet_match.group(4).strip()
            filtered = [
                r for r in filtered
                if start_v <= str(_get_val(r, column) or "").strip()[:len(start_v)] <= end_v
            ]

        # 5. Parse comparisons (>, <, >=, <=) including numbers and ISO dates
        for comp_match in re.finditer(
            r"(?:(\w+)\.)?(\w+)\s*(>=|<=|>|<)\s*(?:['\"]([^'\"]+)['\"]|([0-9.\-]+))",
            where_text, re.IGNORECASE,
        ):
            column = comp_match.group(2).lower()
            op = comp_match.group(3)
            val_str = comp_match.group(4) or comp_match.group(5)

            def compare(row_val, operator, limit_str):
                if row_val is None:
                    return False
                r_str = str(row_val).strip()
                try:
                    # Try numerical comparison first
                    num = float(r_str)
                    lim_num = float(limit_str)
                    if operator == ">": return num > lim_num
                    if operator == "<": return num < lim_num
                    if operator == ">=": return num >= lim_num
                    if operator == "<=": return num <= lim_num
                except (ValueError, TypeError):
                    # Fallback to ISO string / date comparison
                    l_val = limit_str[:len(r_str)]
                    r_val = r_str[:len(limit_str)]
                    if operator == ">": return r_str > limit_str
                    if operator == "<": return r_str < limit_str
                    if operator == ">=": return r_str >= limit_str
                    if operator == "<=": return r_str <= limit_str
                return False

            filtered = [r for r in filtered if compare(_get_val(r, column), op, val_str)]

        # 6. Parse IS NOT NULL / IS NULL conditions
        for ne_match in re.finditer(
            r"(?:(\w+)\.)?(\w+)\s*(?:IS\s+NOT|!=|<>)\s*(?:NULL|null)",
            where_text, re.IGNORECASE,
        ):
            column = ne_match.group(2).lower()
            filtered = [r for r in filtered if _get_val(r, column) is not None]

        for null_match in re.finditer(
            r"(?:(\w+)\.)?(\w+)\s+IS\s+NULL",
            where_text, re.IGNORECASE,
        ):
            column = null_match.group(2).lower()
            filtered = [r for r in filtered if _get_val(r, column) is None or str(_get_val(r, column)).strip() == ""]

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
