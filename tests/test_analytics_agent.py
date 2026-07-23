"""
Tests for AnalyticsAgent.
"""

from __future__ import annotations

import json
from logging import Logger
from unittest.mock import create_autospec

import pytest

from ai import AnalyticsAgent, GroqLLM
from database.queries import AnalyticsRepository
from utils.exceptions import ServiceError


SAMPLE_SNAPSHOT = {
    "total_headcount": 150,
    "by_department": [
        {"department": "Engineering", "count": 60},
        {"department": "Sales", "count": 40},
    ],
    "by_status": [
        {"status": "Active", "count": 140},
        {"status": "On Leave", "count": 10},
    ],
    "by_gender": [
        {"gender": "Male", "count": 80},
        {"gender": "Female", "count": 70},
    ],
    "hiring_by_year": [
        {"year": 2024, "hires": 50},
        {"year": 2025, "hires": 100},
    ],
    "hiring_by_month": [
        {"month": "2025-01", "hires": 10},
    ],
    "average_tenure_years": 3.5,
    "tenure_distribution": [
        {"bucket": "1-3 years", "count": 60},
        {"bucket": "3-5 years", "count": 40},
    ],
}


@pytest.fixture
def repo():
    mock = create_autospec(AnalyticsRepository, instance=True)
    mock.full_snapshot.return_value = SAMPLE_SNAPSHOT
    return mock


@pytest.fixture
def llm():
    return create_autospec(GroqLLM, instance=True)


@pytest.fixture
def logger():
    return create_autospec(Logger, instance=True)


@pytest.fixture
def agent(repo, llm, logger):
    return AnalyticsAgent(
        analytics_repo=repo,
        llm=llm,
        logger=logger,
    )


class TestFullSnapshot:
    def test_returns_all_metrics(self, agent):
        data = agent.full_snapshot()
        assert data["total_headcount"] == 150
        assert len(data["by_department"]) == 2
        assert len(data["hiring_by_year"]) == 2
        assert data["average_tenure_years"] == 3.5

    def test_wraps_error(self, agent, repo):
        repo.full_snapshot.side_effect = Exception("DB down")
        with pytest.raises(ServiceError):
            agent.full_snapshot()


class TestExplainSnapshot:
    def test_returns_explanation(self, agent, llm):
        llm.generate.return_value = (
            "We have 150 employees, with Engineering as the largest "
            "department at 60 people."
        )
        explanation = agent.explain_snapshot()
        assert "150" in explanation
        assert "Engineering" in explanation

    def test_wraps_llm_error(self, agent, llm):
        llm.generate.side_effect = Exception("LLM down")
        with pytest.raises(ServiceError):
            agent.explain_snapshot()


class TestAnswerQuestion:
    def test_answers_specific_question(self, agent, llm):
        # First call = metric selection, second = explanation
        llm.generate.side_effect = [
            json.dumps(["total_headcount", "by_department"]),
            "Engineering has 60 employees, Sales has 40.",
        ]
        answer = agent.answer_question("How many per department?")
        assert "Engineering" in answer

    def test_defaults_to_headcount_on_bad_metric_selection(
        self, agent, llm,
    ):
        llm.generate.side_effect = [
            "not valid json",
            "We have 150 employees.",
        ]
        answer = agent.answer_question("How many people?")
        assert "150" in answer or "employees" in answer
