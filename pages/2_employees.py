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
        "<h3>➕ Create New Employee</h3>"
        "<p style='color:#64748B;font-size:0.9rem;'>Fill in the employee credentials and role details below.</p>",
        unsafe_allow_html=True,
    )

    with st.form("create_form", clear_on_submit=True):
        st.markdown("##### 📌 Basic Credentials")
        col1, col2, col3 = st.columns(3)
        with col1:
            new_no = st.text_input("Employee Number *", placeholder="e.g. EMP1776")
        with col2:
            new_name = st.text_input("Full Name *", placeholder="e.g. Jeevan Pranav")
        with col3:
            new_email = st.text_input("Email Address *", placeholder="e.g. jeevan@company.com")

        st.markdown("##### 🏢 Role & Organization")
        col4, col5, col6 = st.columns(3)
        with col4:
            new_dept = st.selectbox("Department *", ["AI", "Engineering", "Sales", "HR", "Marketing", "Finance", "Operations", "Product"])
        with col5:
            new_position = st.text_input("Position Title *", placeholder="e.g. AI Intern / Software Engineer")
        with col6:
            new_type = st.selectbox("Employment Type *", ["Full Time", "Part Time", "Intern", "Contract"])

        st.markdown("##### 📅 Timeline, Location & Background")
        col7, col8, col9 = st.columns(3)
        with col7:
            from datetime import date
            new_joining_date = st.date_input("Joining Date *", value=date.today())
        with col8:
            new_location = st.text_input("Work Location", placeholder="e.g. Chennai, Bangalore, Remote")
        with col9:
            new_phone = st.text_input("Phone Number", placeholder="e.g. +91 9876543210")

        col10, col11 = st.columns(2)
        with col10:
            new_address = st.text_input("Full Address / Residence", placeholder="e.g. 123 Tech Park, Anna Nagar, Chennai")
        with col11:
            new_work_hist = st.text_input("Work History & Prior Experience", placeholder="e.g. 3 years as AI Specialist at GlobalTech")

        new_status = st.radio("Employment Status", ["Active", "Inactive"], horizontal=True)

        if st.form_submit_button("🚀 Create Employee Record", type="primary", use_container_width=True):
            if not new_no or not new_name:
                st.error("⚠️ Employee Number and Full Name are strictly required.")
            else:
                try:
                    from models.employee import EmployeeCreate
                    emp_no_clean = new_no.strip()
                    name_clean = new_name.strip()
                    is_act = (new_status == "Active")

                    data = EmployeeCreate(
                        employee_no=emp_no_clean,
                        full_name=name_clean,
                        is_active=is_act,
                    )
                    result = st.session_state.emp_service.create_employee(data)

                    # Persist child credentials and work history
                    st.session_state.emp_service.save_employee_details(
                        emp_no_clean,
                        email=new_email.strip() if new_email else None,
                        phone=new_phone.strip() if new_phone else None,
                        employment_type=new_type,
                        joining_date=str(new_joining_date),
                        status=new_status,
                        work_location=new_location.strip() if new_location else None,
                        department=new_dept,
                        position_title=new_position.strip() if new_position else None,
                        full_address=new_address.strip() if new_address else None,
                        work_history_note=new_work_hist.strip() if new_work_hist else None,
                    )

                    st.success(f"✅ Employee **{result.full_name}** (`{result.employee_no}`) created successfully with complete credentials!")
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
