"""
Employees page — search, view, create, update, and manage employee records.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui_helpers import (
    load_css,
    render_sidebar,
    status_badge,
    empty_state,
    show_error,
)

st.set_page_config(
    page_title="👤 Employees",
    page_icon="👤",
    layout="wide",
)

load_css()
render_sidebar()

st.markdown(
    '<h2 style="color:#1A365D;margin:0 0 0.5rem;">👤 Employee Management</h2>',
    unsafe_allow_html=True,
)

# ---- Lazy init EmployeeService ----
if "emp_service" not in st.session_state:
    try:
        from config import get_settings
        from database.client import DatabaseClient
        from database.queries import (
            EmployeeRepository, EmployeeHistoryRepository,
        )
        from services import EmployeeService, EmployeeHistoryService
        from utils.logger import get_logger

        logger = get_logger("employees_page")
        DatabaseClient.get_client()  # ensure singleton initialized
        repo = EmployeeRepository()
        history_repo = EmployeeHistoryRepository()
        history_service = EmployeeHistoryService(history_repo, logger)
        st.session_state.emp_service = EmployeeService(
            repository=repo,
            logger=logger,
            history_service=history_service,
        )

        # Also fetch all employees once
        st.session_state.employees = st.session_state.emp_service.list_all_employees()
    except Exception as exc:
        st.session_state.emp_service = None
        st.session_state.employees = []
        st.error(f"Failed to connect to database: {exc}")


# ---- Tabs ----
tab_list, tab_create, tab_search = st.tabs(["📋 All Employees", "➕ Create", "🔍 Search"])

# ============================================================
# Tab: All Employees
# ============================================================
with tab_list:
    if not st.session_state.employees:
        empty_state("👤", "No employees found", "Create your first employee using the Create tab.")
    else:
        emp_data = [
            {
                "Employee No": e.employee_no,
                "Name": e.full_name,
                "Status": status_badge(e.is_active),
                "Created": e.created_at.date() if e.created_at else "",
            }
            for e in st.session_state.employees
        ]
        df = pd.DataFrame(emp_data)

        st.markdown(
            f'<p style="color:#64748B;font-size:0.85rem;">'
            f"Showing {len(st.session_state.employees)} employees</p>",
            unsafe_allow_html=True,
        )

        st.write(df.to_html(escape=False, index=False), unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("Quick Actions")

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            emp_no = st.selectbox(
                "Select Employee",
                options=[e.employee_no for e in st.session_state.employees],
                key="list_select",
            )
        with col_b:
            if st.button("View Profile", use_container_width=True):
                profile = st.session_state.emp_service.get_full_profile(emp_no)
                if profile:
                    st.markdown(
                        f'<div class="card">'
                        f"<h3>{profile.full_name}</h3>"
                        f"<p><strong>EMP:</strong> {profile.employee_no}</p>"
                        f"<p><strong>Department:</strong> {profile.department or 'N/A'}</p>"
                        f"<p><strong>Position:</strong> {profile.position_title or 'N/A'}</p>"
                        f"<p><strong>Status:</strong> {status_badge(profile.is_active, profile.status)}</p>"
                        f"<p><strong>Email:</strong> {profile.email or 'N/A'}</p>"
                        f"<p><strong>Phone:</strong> {profile.phone or 'N/A'}</p>"
                        f"<p><strong>Joined:</strong> {profile.joining_date or 'N/A'}</p>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

        with col_c:
            action = st.radio("Action", ["Activate", "Deactivate"], horizontal=True)
            if st.button("Apply", use_container_width=True, type="primary"):
                try:
                    if action == "Activate":
                        st.session_state.emp_service.activate_employee(emp_no)
                    else:
                        st.session_state.emp_service.deactivate_employee(emp_no)
                    st.success(f"Employee {emp_no} {action.lower()}d.")
                    st.session_state.employees = (
                        st.session_state.emp_service.list_all_employees()
                    )
                    st.rerun()
                except Exception as exc:
                    show_error(str(exc))

# ============================================================
# Tab: Create
# ============================================================
with tab_create:
    st.markdown(
        '<div class="card">'
        "<h3>New Employee</h3>",
        unsafe_allow_html=True,
    )

    with st.form("create_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_no = st.text_input("Employee Number *", placeholder="e.g. EMP010")
        with col2:
            new_name = st.text_input("Full Name *", placeholder="e.g. Jane Smith")
        new_active = st.checkbox("Active", value=True)

        if st.form_submit_button("Create Employee", type="primary"):
            if not new_no or not new_name:
                st.error("Employee Number and Full Name are required.")
            else:
                try:
                    from models.employee import EmployeeCreate
                    data = EmployeeCreate(
                        employee_no=new_no.strip(),
                        full_name=new_name.strip(),
                        is_active=new_active,
                    )
                    result = st.session_state.emp_service.create_employee(data)
                    st.success(f"✅ {result.full_name} ({result.employee_no}) created.")
                    st.session_state.employees = (
                        st.session_state.emp_service.list_all_employees()
                    )
                except Exception as exc:
                    show_error(str(exc))

    st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# Tab: Search
# ============================================================
with tab_search:
    with st.form("search_form"):
        search_query = st.text_input(
            "Search by name or employee number",
            placeholder="e.g. John or EMP001",
        )
        dept = st.text_input("Department filter (optional)")
        col1, col2 = st.columns(2)
        with col1:
            active_filter = st.selectbox(
                "Status", ["All", "Active", "Inactive"],
            )
        with col2:
            position_filter = st.text_input("Position title (optional)")

        if st.form_submit_button("Search", type="primary"):
            is_active = (
                None if active_filter == "All"
                else (active_filter == "Active")
            )
            try:
                results = st.session_state.emp_service.search_employees(
                    query=search_query or None,
                    is_active=is_active,
                    department=dept or None,
                    position_title=position_filter or None,
                )
                if not results:
                    empty_state("🔍", "No results", "Try different search terms.")
                else:
                    df = pd.DataFrame([
                        {
                            "Employee No": e.employee_no,
                            "Name": e.full_name,
                            "Status": status_badge(e.is_active),
                        }
                        for e in results
                    ])
                    st.write(df.to_html(escape=False, index=False), unsafe_allow_html=True)
            except Exception as exc:
                show_error(str(exc))
