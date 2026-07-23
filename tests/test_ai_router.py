"""
Tests for the AI Router (intent classification).
"""

from __future__ import annotations

from logging import Logger
from unittest.mock import MagicMock, create_autospec

import pytest

from ai import AIRouter, GroqLLM, IntentType, RouterDecision
from utils.exceptions import ServiceError


@pytest.fixture
def llm():
    return create_autospec(GroqLLM, instance=True)


@pytest.fixture
def logger():
    return create_autospec(Logger, instance=True)


@pytest.fixture
def router(llm, logger):
    return AIRouter(llm=llm, logger=logger)


def _make_json(intent: str, reasoning: str, confidence: float) -> str:
    """Helper: build the JSON string the mock LLM returns."""
    import json
    return json.dumps({
        "intent": intent,
        "reasoning": reasoning,
        "confidence": confidence,
    })


# ====================================================================
# classify — happy path per intent
# ====================================================================


class TestClassifyHappyPath:
    def test_classifies_crud(self, router, llm):
        llm.generate.return_value = _make_json(
            "CRUD", "User wants to look up an employee", 0.95,
        )
        decision = router.classify("Show me John Doe's details")
        assert decision.intent == IntentType.CRUD
        assert 0.0 <= decision.confidence <= 1.0

    def test_classifies_analytics(self, router, llm):
        llm.generate.return_value = _make_json(
            "Analytics", "User is asking for a count breakdown", 0.90,
        )
        decision = router.classify("How many employees per department?")
        assert decision.intent == IntentType.ANALYTICS

    def test_classifies_semantic_search(self, router, llm):
        llm.generate.return_value = _make_json(
            "SemanticSearch", "User wants to find by skill", 0.88,
        )
        decision = router.classify(
            "Find someone with experience in Python"
        )
        assert decision.intent == IntentType.SEMANTIC_SEARCH

    def test_classifies_sql(self, router, llm):
        llm.generate.return_value = _make_json(
            "SQL", "Factual query that needs a DB lookup", 0.92,
        )
        decision = router.classify("Who joined the company last month?")
        assert decision.intent == IntentType.SQL

    def test_classifies_history(self, router, llm):
        llm.generate.return_value = _make_json(
            "History", "User wants a career timeline", 0.90,
        )
        decision = router.classify("Show me Rahul's history")
        assert decision.intent == IntentType.HISTORY

    def test_classifies_stall_query_as_history(self, router, llm):
        llm.generate.return_value = _make_json(
            "History", "Stall detection", 0.85,
        )
        decision = router.classify(
            "Whose career has stalled for 4+ years?"
        )
        assert decision.intent == IntentType.HISTORY

    def test_classify_appends_context(self, router, llm):
        llm.generate.return_value = _make_json(
            "SQL", "Follow-up question", 0.85,
        )
        context = [{"role": "assistant", "content": "Previous answer"}]
        router.classify("And how many are in Engineering?", context=context)
        # Verify build_messages received the context
        _, kwargs = llm.build_messages.call_args
        assert kwargs.get("context") == context


# ====================================================================
# classify — edge cases
# ====================================================================


class TestClassifyEdgeCases:
    def test_handles_markdown_fenced_json(self, router, llm):
        llm.generate.return_value = "```json\n{\"intent\": \"SQL\", \"reasoning\": \"test\", \"confidence\": 0.8}\n```"
        decision = router.classify("test")
        assert decision.intent == IntentType.SQL

    def test_handles_plain_backtick_fence(self, router, llm):
        llm.generate.return_value = "```\n{\"intent\": \"CRUD\", \"reasoning\": \"test\", \"confidence\": 0.7}\n```"
        decision = router.classify("test")
        assert decision.intent == IntentType.CRUD

    def test_clamps_high_confidence(self, router, llm):
        llm.generate.return_value = _make_json("SQL", "test", 1.5)
        decision = router.classify("test")
        assert decision.confidence == 1.0

    def test_clamps_low_confidence(self, router, llm):
        llm.generate.return_value = _make_json("SQL", "test", -0.5)
        decision = router.classify("test")
        assert decision.confidence == 0.0

    def test_defaults_missing_fields(self, router, llm):
        llm.generate.return_value = '{"intent": "CRUD"}'
        decision = router.classify("test")
        assert decision.intent == IntentType.CRUD
        assert isinstance(decision.reasoning, str)
        assert 0.0 <= decision.confidence <= 1.0


# ====================================================================
# classify — error handling
# ====================================================================


class TestClassifyErrors:
    def test_raises_service_error_on_unparseable_json(self, router, llm):
        llm.generate.return_value = "not valid json"
        with pytest.raises(ServiceError):
            router.classify("test")

    def test_raises_service_error_on_unknown_intent(self, router, llm):
        llm.generate.return_value = _make_json(
            "UnknownIntent", "hmm", 0.5,
        )
        with pytest.raises(ServiceError, match="Unknown intent"):
            router.classify("test")

    def test_wraps_llm_error_in_service_error(self, router, llm):
        from utils.exceptions import LlmError
        llm.generate.side_effect = LlmError("LLM down")
        with pytest.raises(ServiceError, match="LLM classification failed"):
            router.classify("test")


# ====================================================================
# _parse_decision — unit tests
# ====================================================================


class TestParseDecision:
    def test_parses_valid_json(self):
        decision = AIRouter._parse_decision(
            '{"intent": "Analytics", "reasoning": "count", "confidence": 0.9}'
        )
        assert decision.intent == IntentType.ANALYTICS
        assert decision.reasoning == "count"
        assert decision.confidence == 0.9

    def test_parses_with_extra_whitespace(self):
        decision = AIRouter._parse_decision(
            '  {"intent": "SQL","reasoning":"x","confidence":0.5}  '
        )
        assert decision.intent == IntentType.SQL

    def test_raises_on_bad_json(self):
        with pytest.raises(ServiceError):
            AIRouter._parse_decision("{bad json}")

    def test_raises_on_unknown_intent(self):
        with pytest.raises(ServiceError, match="Unknown intent"):
            AIRouter._parse_decision(
                '{"intent": "FooBar", "reasoning": "x", "confidence": 0}'
            )
