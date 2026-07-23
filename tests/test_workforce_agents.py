"""
Tests for the Part-6 workforce agents.

Covers that each agent:
  - Produces a scored, explainable result.
  - Each result carries an Explanation with itemized reasons.
  - Scoring factors are reasonable and fall in [0, 1].
"""

from __future__ import annotations

from logging import Logger
from unittest.mock import create_autospec, MagicMock

import pytest

from models.employee import Employee
from models.history import (
    CareerStats,
    EmployeeTimeline,
    Explanation,
    ExplanationReason,
    HistoryEventType,
    TimelineEntry,
)
from models.responses import EmployeeProfileResponse
from services.workforce_agents import (
    RecommendationEngine,
    TeamBuilder,
    PromotionAnalyzer,
    TransferAnalyzer,
    AttritionRisk,
    SkillGapAgent,
    InsightAgent,
)

from .conftest import make_employee_row


def _emp(**overrides):
    return Employee.model_validate(make_employee_row(**overrides))


def _profile(**overrides):
    base = {
        "employee_no": "EMP001",
        "full_name": "Test",
        "is_active": True,
    }
    base.update(overrides)
    return EmployeeProfileResponse(**base)


def _timeline(**stats_overrides):
    stats = CareerStats(
        total_tenure_days=365 * 3,
        time_in_each_role={"Engineer": 365 * 3},
        promotions_count=1,
        time_since_last_promotion_days=365 * 2,
        average_time_between_promotions_days=None,
        is_stalled=False,
        stall_threshold_days=365 * 4,
    )
    for k, v in stats_overrides.items():
        setattr(stats, k, v)
    return EmployeeTimeline(
        employee_no="EMP001",
        full_name="Test",
        events=[
            TimelineEntry(
                event_type=HistoryEventType.HIRED,
                occurred_at=__import__("datetime").datetime(2022, 1, 1),
                description="Hired",
            ),
        ],
        stats=stats,
    )


@pytest.fixture
def emp_service():
    """Mock EmployeeService with the methods the workforce agents call."""
    mock = MagicMock()
    mock.list_all_employees = MagicMock()
    mock.get_full_profile = MagicMock()
    mock.search_employees = MagicMock()
    mock.get_employee_by_no = MagicMock()
    return mock


@pytest.fixture
def history_service():
    """Mock EmployeeHistoryService with the method needed."""
    mock = MagicMock()
    mock.build_timeline = MagicMock()
    mock.log_event = MagicMock()
    return mock


@pytest.fixture
def analytics_agent():
    """Mock AnalyticsAgent with the methods needed."""
    mock = MagicMock()
    mock.full_snapshot = MagicMock()
    mock.explain_snapshot = MagicMock()
    mock.answer_question = MagicMock()
    return mock


@pytest.fixture
def logger():
    return create_autospec(Logger, instance=True)


# ====================================================================
# Recommendation Engine
# ====================================================================


class TestRecommendationEngine:
    def test_recommend_returns_scored_items(self, emp_service, history_service, logger):
        engine = RecommendationEngine(emp_service, history_service, logger)
        emp = _emp()
        emp_service.list_all_employees.return_value = [emp]
        emp_service.get_full_profile.return_value = _profile(
            department="Engineering",
            position_title="Backend Developer",
            city="Chennai",
        )
        history_service.build_timeline.return_value = _timeline()

        results = engine.recommend(
            role="Backend Developer",
            department="Engineering",
            location="Chennai",
        )
        assert len(results) > 0
        item = results[0]
        assert "score" in item
        assert 0.0 <= item["score"] <= 1.0
        assert isinstance(item["explanation"], Explanation)
        reasons = item["explanation"].reasons
        assert any(r.factor == "Department match" for r in reasons)
        assert any(r.factor == "Title overlap" for r in reasons)
        assert any(r.factor == "Location" for r in reasons)
        assert any(r.factor == "Tenure / experience" for r in reasons)

    def test_empty_pool_returns_empty_list(self, emp_service, history_service, logger):
        engine = RecommendationEngine(emp_service, history_service, logger)
        emp_service.list_all_employees.return_value = []
        assert engine.recommend(role="anything") == []


# ====================================================================
# Team Builder
# ====================================================================


class TestTeamBuilder:
    def test_build_returns_slots_with_explanations(
        self, emp_service, history_service, logger,
    ):
        rec = RecommendationEngine(emp_service, history_service, logger)
        builder = TeamBuilder(rec, logger)

        emp = _emp()
        emp_service.list_all_employees.return_value = [emp, _emp(employee_no="EMP002")]
        emp_service.get_full_profile.return_value = _profile(
            department="Engineering",
            position_title="Backend Developer",
        )
        history_service.build_timeline.return_value = _timeline()

        result = builder.build(
            "AI healthcare project",
            roles=["Backend Developer", "ML Engineer"],
        )
        assert len(result["slots"]) >= 1
        for s in result["slots"]:
            assert isinstance(s["explanation"], Explanation)
        assert "summary" in result

    def test_reports_unfilled_roles(
        self, emp_service, history_service, logger,
    ):
        rec = RecommendationEngine(emp_service, history_service, logger)
        builder = TeamBuilder(rec, logger)
        emp_service.list_all_employees.return_value = []  # no employees
        result = builder.build(
            "Project Delta", roles=["QA Engineer"],
        )
        assert len(result["slots"]) == 0
        assert "QA Engineer" in result["unfilled"]


# ====================================================================
# Promotion Analyzer
# ====================================================================


class TestPromotionAnalyzer:
    def test_analyze_returns_scored_with_reasons(
        self, history_service, emp_service, logger,
    ):
        analyzer = PromotionAnalyzer(history_service, emp_service, logger)
        emp_service.list_all_employees.return_value = [_emp()]
        timeline = _timeline(
            time_since_last_promotion_days=365 * 6,
            is_stalled=True,
        )
        history_service.build_timeline.return_value = timeline

        results = analyzer.analyze()
        assert len(results) > 0
        item = results[0]
        assert 0.0 <= item["score"] <= 1.0
        assert isinstance(item["explanation"], Explanation)
        reasons = item["explanation"].reasons
        assert any(r.factor == "Time since last promotion" for r in reasons)
        assert any(r.factor == "Tenure" for r in reasons)
        assert any(r.factor == "Prior promotions count" for r in reasons)
        assert any(r.factor == "Stalled" for r in reasons)

    def test_no_employees_returns_empty(self, history_service, emp_service, logger):
        analyzer = PromotionAnalyzer(history_service, emp_service, logger)
        emp_service.list_all_employees.return_value = []
        assert analyzer.analyze() == []


# ====================================================================
# Transfer Analyzer
# ====================================================================


class TestTransferAnalyzer:
    def test_analyze_returns_transfer_suggestions(
        self, emp_service, history_service, analytics_agent, logger,
    ):
        analyzer = TransferAnalyzer(
            emp_service, history_service, analytics_agent, logger,
        )
        emp_service.list_all_employees.return_value = [_emp()]
        emp_service.get_full_profile.return_value = _profile(
            department="Sales",
        )
        history_service.build_timeline.return_value = _timeline(
            total_tenure_days=365 * 3,
        )
        analytics_agent.full_snapshot.return_value = {
            "by_department": [
                {"department": "Engineering", "count": 10},
                {"department": "Sales", "count": 3},
            ],
        }

        results = analyzer.analyze()
        assert len(results) > 0
        item = results[0]
        assert item["from_department"] == "Sales"
        assert item["to_department"] == "Engineering"
        assert isinstance(item["explanation"], Explanation)


# ====================================================================
# Attrition Risk
# ====================================================================


class TestAttritionRisk:
    def test_analyze_returns_risk_assessments(
        self, history_service, emp_service, analytics_agent, logger,
    ):
        risk_agent = AttritionRisk(
            history_service, emp_service, analytics_agent, logger,
        )
        emp_service.list_all_employees.return_value = [_emp()]
        emp_service.get_full_profile.return_value = _profile(
            department="Engineering",
            position_title="Staff Engineer",
        )
        timeline = _timeline(
            total_tenure_days=365 * 10,
            time_since_last_promotion_days=365 * 8,
            promotions_count=0,
            is_stalled=True,
            time_in_each_role={"Staff Engineer": 365 * 8},
        )
        history_service.build_timeline.return_value = timeline
        analytics_agent.full_snapshot.return_value = {
            "fastest_growing_department": [
                {"department": "Engineering", "hires": 5},
            ],
        }

        results = risk_agent.analyze()
        assert len(results) > 0
        item = results[0]
        assert "indicators" in item
        assert isinstance(item["explanation"], Explanation)
        reasons = item["explanation"].reasons
        assert any(r.factor == "Career stalled" for r in reasons)
        assert any(r.factor == "Department churn" for r in reasons)


# ====================================================================
# Skill Gap Agent
# ====================================================================


class TestSkillGapAgent:
    def test_analyze_returns_cost_estimation_with_placeholder_note(
        self, emp_service, analytics_agent, logger,
    ):
        agent = SkillGapAgent(emp_service, analytics_agent, logger)
        # Create 10 active employees so a 40% growth = 4 hires.
        emps = [
            _emp(employee_no=f"EMP{str(i).zfill(3)}", employee_id=i)
            for i in range(1, 11)
        ]
        emp_service.list_all_employees.return_value = emps
        emp_service.get_full_profile.return_value = _profile(
            department="AI Division", city="Bangalore",
        )
        analytics_agent.full_snapshot.return_value = {
            "total_headcount": 10,
            "by_department": [
                {"department": "AI Division", "count": 5},
            ],
        }

        result = agent.analyze(
            "Grow the AI division 40% under budget",
            growth_pct=40.0,
        )
        assert "cost_assumption" in result
        assert "PLACEHOLDER" in result["cost_assumption"].upper()
        assert result["estimated_hires"] > 0
        assert isinstance(result["explanation"], Explanation)

    def test_analyze_infers_roles_when_not_given(
        self, emp_service, analytics_agent, logger,
    ):
        agent = SkillGapAgent(emp_service, analytics_agent, logger)
        emp_service.list_all_employees.return_value = [_emp()]
        emp_service.get_full_profile.return_value = _profile()
        analytics_agent.full_snapshot.return_value = {
            "total_headcount": 10,
            "by_department": [],
        }
        result = agent.analyze(
            "New AI research centre in Hyderabad",
        )
        assert len(result["required_roles"]) > 0


# ====================================================================
# Insight Agent
# ====================================================================


class TestInsightAgent:
    def test_full_scorecard_returns_explained_metrics(
        self, analytics_agent, logger,
    ):
        agent = InsightAgent(analytics_agent, logger)

        analytics_agent.full_snapshot.return_value = {
            "total_headcount": 50,
            "average_tenure_years": 3.2,
        }
        # Mock the internal repository. Use a MagicMock so we can
        # attach ``insight_snapshot``.
        mock_repo = MagicMock()
        mock_repo.insight_snapshot.return_value = {
            "total_headcount": 50,
            "average_tenure_years": 3.2,
            "fastest_growing_department": [
                {"department": "AI", "hires": 8},
            ],
            "largest_engineering_hub": [
                {"city": "Bangalore", "count": 23},
            ],
            "understaffed_departments": [
                {"department": "QA", "count": 2, "percent_of_total": 4.0},
            ],
            "hiring_forecast": {
                "year": [2023, 2024],
                "hires": [10, 12],
                "avg_hires_per_year": 11.0,
                "projected_next_year_hires": 11.0,
                "note": "Based on the average of the last 2 years.",
            },
        }
        analytics_agent._repo = mock_repo

        result = agent.full_scorecard()
        assert "total_headcount" in result
        for key in ("fastest_growing", "largest_hub", "understaffed", "hiring_forecast"):
            section = result[key]
            assert "explanation" in section
            exp = section["explanation"]
            assert isinstance(exp, Explanation)
            assert len(exp.reasons) > 0