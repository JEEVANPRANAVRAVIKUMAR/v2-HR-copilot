"""
Tests for the complexity detector.

Verifies that:
  - Simple questions are NOT flagged as complex (Tier 1).
  - Multi-step / executive questions ARE flagged as complex (Tier 2).
  - Very long messages (> 30 tokens) are treated as complex.
"""

from __future__ import annotations

import pytest
from ai.planner import is_complex


class TestSimpleQuestions:
    def test_single_crud(self):
        assert is_complex("Show me John's details") is False

    def test_single_sql(self):
        assert is_complex("Who joined last month?") is False

    def test_basic_analytics(self):
        assert is_complex("How many employees are there?") is False

    def test_single_history(self):
        assert is_complex("Show me Rahul's history") is False


class TestComplexQuestions:
    def test_multi_step_keyword(self):
        assert is_complex("first find all engineers, then count them") is True

    def test_executive_opening_centre(self):
        assert is_complex(
            "We're opening an AI research centre in Hyderabad; "
            "recommend transfers, find skill gaps, estimate "
            "hiring cost, and summarize."
        ) is True

    def test_assemble_team(self):
        assert is_complex(
            "Build the best team for an AI healthcare project"
        ) is True

    def test_grow_division_keyword(self):
        assert is_complex(
            "Grow the AI division by 40% under budget"
        ) is True

    def test_skill_gap_keyword(self):
        assert is_complex(
            "What is the skill gap for a new DevOps team?"
        ) is True

    def test_internal_mobility(self):
        assert is_complex(
            "Recommend transfers for internal mobility"
        ) is True

    def test_rank_prioritize(self):
        assert is_complex("Rank the promotion candidates") is True

    def test_multi_step_chain(self):
        assert is_complex(
            "Show everyone hired in 2024, group them by "
            "department, then summarize the hiring strategy"
        ) is True


class TestTokenCountFallback:
    def test_very_long_message_is_complex(self):
        long_msg = (
            "we need to analyse the workforce distribution across "
            "all departments and also look at the attrition risk "
            "for engineers in the Bangalore office while also "
            "preparing a hiring forecast for next year"
        )
        # This is >30 tokens.
        assert is_complex(long_msg) is True

    def test_medium_message_is_not_complex(self):
        medium_msg = "list all employees in the Engineering department"
        assert is_complex(medium_msg) is False

    def test_triggers_on_both_keyword_and_length(self):
        msg = (
            "first rank promotion candidates then also compare "
            "attrition risk flags and finally summarize the "
            "transfer recommendations for the Chennai office"
        )
        assert is_complex(msg) is True