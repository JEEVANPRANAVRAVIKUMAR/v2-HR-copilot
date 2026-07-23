"""
Tests for the multi-agent Planner.

Covers:
  - Complexity detection → Tier 1 fallback for simple questions.
  - Plan decomposition (LLM returns a JSON plan).
  - Plan execution with an agent registry.
  - Failed-step handling (partial results).
  - Synthesis of the final answer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from logging import Logger
from unittest.mock import create_autospec, MagicMock

import pytest

from ai import GroqLLM, Planner
from utils.exceptions import ServiceError


@pytest.fixture
def llm():
    return create_autospec(GroqLLM, instance=True)


@pytest.fixture
def logger():
    return create_autospec(Logger, instance=True)


@pytest.fixture
def planner(llm, logger):
    return Planner(llm=llm, logger=logger)


_SIMPLE_PLAN_JSON = (
    '{"summary":"single step", "steps":['
    '{"step":1,"agent":"SQL","sub_question":"Who joined in 2024?",'
    '"purpose":"answer directly","depends_on_output_of":null}],'
    '"max_steps":1}'
)

_MULTI_STEP_PLAN_JSON = (
    '{"summary":"two-step", "steps":['
    '{"step":1,"agent":"SQL","sub_question":"List everyone hired in 2024",'
    '"purpose":"get base list","depends_on_output_of":null},'
    '{"step":2,"agent":"Analytics","sub_question":"Group by department",'
    '"purpose":"summarize","depends_on_output_of":1}],'
    '"max_steps":2}'
)


# ====================================================================
# Tier 1 fallback — simple questions skip the planner
# ====================================================================


class TestTier1Fallback:
    def test_simple_question_returns_tier1(self, planner, llm):
        result = planner.execute(
            "Show me John's details",
            agent_registry={},
        )
        assert result["complex"] is False
        assert result["tier"] == 1
        assert result["answer"] == ""
        assert result["plan"] == []

    def test_short_message_not_complex(self, planner, llm):
        result = planner.execute(
            "How many employees?",
            agent_registry={},
        )
        assert result["complex"] is False


# ====================================================================
# Tier 2 — multi-step plan
# ====================================================================


class TestMultiStepPlan:
    def test_decomposes_and_executes_two_steps(
        self, planner, llm,
    ):
        # LLM returns a two-step plan.
        llm.generate.side_effect = [
            _MULTI_STEP_PLAN_JSON,   # decomposition
            "Hiring was strong in Engineering.",  # synthesis
        ]

        agent_registry = {
            "SQL": lambda msg, ctx, prev: (
                "3 employees hired in 2024"
            ),
            "Analytics": lambda msg, ctx, prev: (
                "Engineering: 2, Sales: 1"
            ),
        }
        result = planner.execute(
            "Show everyone hired in 2024, group them by "
            "department, then summarize the hiring strategy.",
            agent_registry=agent_registry,
        )

        assert result["complex"] is True
        assert result["tier"] == 2
        assert len(result["plan"]) == 2
        assert result["plan"][0]["agent"] == "SQL"
        assert result["plan"][1]["agent"] == "Analytics"
        assert len(result["step_results"]) == 2
        assert result["answer"] == "Hiring was strong in Engineering."
        assert result["failed_steps"] == []

    def test_caps_at_max_steps(self, planner, llm):
        many_steps = {
            "summary": "3 steps",
            "steps": [
                {"step": 1, "agent": "SQL", "sub_question": "a",
                 "purpose": "a", "depends_on_output_of": None},
                {"step": 2, "agent": "Analytics", "sub_question": "b",
                 "purpose": "b", "depends_on_output_of": 1},
                {"step": 3, "agent": "History", "sub_question": "c",
                 "purpose": "c", "depends_on_output_of": 2},
            ],
            "max_steps": 3,
        }
        import json
        plan_json = json.dumps(many_steps)

        llm.generate.side_effect = [
            plan_json,
            "Synthesis result.",
        ]

        agent_registry = {
            "SQL": lambda msg, ctx, prev: "ok",
            "Analytics": lambda msg, ctx, prev: "ok",
            "History": lambda msg, ctx, prev: "ok",
        }
        result = planner.execute(
            "multi-step question",
            agent_registry=agent_registry,
            max_steps=2,
        )
        # Plan was capped to 2 steps.
        assert len(result["plan"]) == 2

    def test_handles_missing_agent_gracefully(
        self, planner, llm,
    ):
        llm.generate.side_effect = [
            _MULTI_STEP_PLAN_JSON,
            "Partial answer — step 2 skipped.",
        ]

        agent_registry = {
            "SQL": lambda msg, ctx, prev: "SQL result",
            # "Analytics" is NOT in the registry.
        }
        # Must use a complex-sounding message so is_complex -> True:
        result = planner.execute(
            "first find everyone in engineering, "
            "group everyone by department, "
            "then also compare attrition numbers",
            agent_registry=agent_registry,
        )
        # The failed step should be recorded.
        assert len(result["failed_steps"]) == 1
        # Step 2 should have failed.
        failed_step_nums = [
            f["step"] for f in result["failed_steps"]
        ]
        assert 2 in failed_step_nums
        # Synthesis should still be called.
        assert len(result["answer"]) > 0

    def test_sub_agent_exception_does_not_crash_planner(
        self, planner, llm,
    ):
        llm.generate.side_effect = [
            _MULTI_STEP_PLAN_JSON,
            "Partial after step 2 failure.",
        ]

        def _broken_analytics(msg, ctx, prev):
            raise Exception("Analytics agent crashed")
            return "never"

        agent_registry = {
            "SQL": lambda msg, ctx, prev: "SQL ok",
            "Analytics": _broken_analytics,
        }
        # Longer message with multi-step keywords:
        result = planner.execute(
            "first analyze the department breakdown, "
            "then compare hiring efficiency across teams, "
            "and summarize the growth strategy",
            agent_registry=agent_registry,
        )
        assert len(result["failed_steps"]) == 1
        assert result["answer"] is not None

    def test_planner_raises_service_error_on_llm_failure(
        self, planner, llm,
    ):
        from utils.exceptions import LlmError
        llm.generate.side_effect = LlmError("LLM down")
        with pytest.raises(ServiceError):
            planner.execute(
                "Open a new research centre in Hyderabad",
                agent_registry={"SQL": lambda *a: "ok"},
            )


# ====================================================================
# Plan parsing edge cases
# ====================================================================


class TestPlanParsing:
    def test_strips_markdown_fence(self):
        raw = '```json\n' + _SIMPLE_PLAN_JSON + '\n```'
        parsed = Planner._parse_plan(raw)
        assert len(parsed["steps"]) == 1

    def test_fallback_on_unparseable_json(self, planner, llm):
        # The decomposition LLM returns garbage — the planner should
        # yield a single-step fallback rather than crashing.
        llm.generate.side_effect = [
            "not valid json at all",
            "Fallback synthesis.",
        ]
        result = planner.execute(
            "We're opening a new centre in Chennai",
            agent_registry={"SQL": lambda *a: "SQL result"},
        )
        # The plan degraded to a fallback single-step.
        assert len(result["plan"]) <= 1
        # It still produced something.
        assert "answer" in result

    def test_handles_no_steps_in_plan(self):
        parsed = Planner._parse_plan('{"summary":"empty","steps":[]}')
        assert parsed["steps"] == []