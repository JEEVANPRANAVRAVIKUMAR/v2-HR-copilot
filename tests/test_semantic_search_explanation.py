"""
Tests for the Scope-3 explanation features on
SemanticSearchAgent.

These verify that:
  - ``search_scored`` returns rows with an ``Explanation`` object
    attached and properly-shaped factors.
  - ``explain`` returns the explanation for a specific employee, or
    an "empty" explanation if they weren't a hit.
"""

from __future__ import annotations

from logging import Logger
from unittest.mock import create_autospec, patch

import pytest

from ai import GroqLLM, SemanticSearchAgent, EmbeddingGenerator
from database.queries import EmbeddingRepository
from models.history import Explanation, ExplanationReason


@pytest.fixture
def embedder():
    e = create_autospec(EmbeddingGenerator, instance=True)
    e.embed_query.return_value = [0.1, 0.2, 0.3]
    return e


@pytest.fixture
def emb_repo():
    return create_autospec(EmbeddingRepository, instance=True)


@pytest.fixture
def llm():
    return create_autospec(GroqLLM, instance=True)


@pytest.fixture
def logger():
    return create_autospec(Logger, instance=True)


@pytest.fixture
def agent(embedder, emb_repo, llm, logger):
    return SemanticSearchAgent(embedder, emb_repo, llm, logger)


def _row(
    *,
    employee_no="EMP010",
    full_name="Alice Lee",
    department="Engineering",
    position_title="Senior Engineer",
    similarity=0.82,
) -> dict:
    return {
        "employee_no": employee_no,
        "full_name": full_name,
        "department": department,
        "position_title": position_title,
        "similarity": similarity,
    }


# ====================================================================
# search_scored
# ====================================================================


class TestSearchScored:
    def test_attaches_explanation_to_each_row(self, agent, emb_repo):
        emb_repo.search.return_value = [
            _row(employee_no="EMP010", full_name="Alice"),
            _row(employee_no="EMP011", full_name="Bob", similarity=0.55),
        ]
        results = agent.search_scored("python engineer")
        assert len(results) == 2
        for r in results:
            assert "explanation" in r
            assert isinstance(r["explanation"], Explanation)
            # `score` at the top-level should be the raw similarity
            # whereas `explanation.score` is the weighted combo.
            assert r["score"] in (0.55, 0.82)
            # The explanation score must lie in [0, 1].
            assert 0.0 <= r["explanation"].score <= 1.0

    def test_results_sorted_by_score_desc(self, agent, emb_repo):
        emb_repo.search.return_value = [
            _row(employee_no="EMP011", full_name="Bob", similarity=0.45),
            _row(employee_no="EMP010", full_name="Alice", similarity=0.85),
        ]
        results = agent.search_scored("python engineer", threshold=0.4)
        assert results[0]["employee_no"] == "EMP010"  # 0.85 first
        assert results[1]["employee_no"] == "EMP011"

    def test_explanation_contains_semantic_factor(self, agent, emb_repo):
        emb_repo.search.return_value = [_row(similarity=0.82)]
        results = agent.search_scored("python engineer", threshold=0.5)
        exp = results[0]["explanation"]
        factors = {r.factor for r in exp.reasons}
        assert "Semantic similarity" in factors
        # The "Semantic similarity" reason should be marked as met
        # since 0.82 > 0.5.
        sim_reason = next(r for r in exp.reasons if r.factor == "Semantic similarity")
        assert sim_reason.is_met is True

    def test_explanation_contains_term_overlap_factor(self, agent, emb_repo):
        # The query "python engineer" overlaps with row having position "Engineer"
        emb_repo.search.return_value = [
            _row(full_name="Alice", position_title="Senior Engineer"),
        ]
        results = agent.search_scored("python engineer", threshold=0.5)
        factors = {r.factor for r in results[0]["explanation"].reasons}
        assert "Query term overlap" in factors

    def test_term_overlap_factor_attaches_detail_with_counts(
        self, agent, emb_repo,
    ):
        emb_repo.search.return_value = [
            _row(full_name="Python Dev", position_title="Engineer"),
        ]
        results = agent.search_scored("python engineer", threshold=0.4)
        reas = next(
            r for r in results[0]["explanation"].reasons
            if r.factor == "Query term overlap"
        )
        # Detail should mention how many terms matched
        assert reas.detail is not None
        assert "/" in reas.detail

    def test_factor_above_threshold_met_when_score_high(self, agent, emb_repo):
        emb_repo.search.return_value = [_row(similarity=0.85)]
        results = agent.search_scored("python", threshold=0.5)
        reas = next(
            r for r in results[0]["explanation"].reasons
            if r.factor == "Above threshold"
        )
        assert reas.is_met is True

    def test_factor_above_threshold_not_met_when_score_low(self, agent, emb_repo):
        emb_repo.search.return_value = [_row(similarity=0.2)]
        results = agent.search_scored("python", threshold=0.5)
        reas = next(
            r for r in results[0]["explanation"].reasons
            if r.factor == "Above threshold"
        )
        assert reas.is_met is False

    def test_explanation_summary_includes_name_and_score(self, agent, emb_repo):
        emb_repo.search.return_value = [
            _row(full_name="Alice Lee", similarity=0.7),
        ]
        results = agent.search_scored("python", threshold=0.5)
        summary = results[0]["explanation"].summary
        assert "Alice Lee" in summary
        assert "score" in summary.lower()

    def test_threshold_propagates_to_search_call(self, agent, emb_repo):
        emb_repo.search.return_value = []
        agent.search_scored("python", top_k=3, threshold=0.65)
        # The repository's search should have been called with the
        # propagated parameters.
        _args, _kwargs = emb_repo.search.call_args
        assert _kwargs["match_threshold"] == 0.65
        assert _kwargs["match_count"] == 3


# ====================================================================
# explain
# ====================================================================


class TestExplain:
    def test_explain_returns_explanation_for_matching_employee(self, agent, emb_repo):
        emb_repo.search.return_value = [
            _row(employee_no="EMP010", full_name="Alice", similarity=0.78),
            _row(employee_no="EMP011", full_name="Bob", similarity=0.5),
        ]
        exp = agent.explain("python", "EMP010", threshold=0.5)
        assert isinstance(exp, Explanation)
        assert exp.score > 0
        # Has reasons with the expected factors.
        factors = {r.factor for r in exp.reasons}
        assert "Semantic similarity" in factors

    def test_explain_returns_empty_explanation_for_non_match(self, agent, emb_repo):
        emb_repo.search.return_value = [
            _row(employee_no="EMP010", full_name="Alice"),
        ]
        exp = agent.explain("python", "EMP999", threshold=0.5)
        assert exp.score == 0.0
        assert all(r.is_met is False for r in exp.reasons)
        # Has a summary mentioning that the employee wasn't a match.
        assert "not returned" in exp.summary.lower()


# ====================================================================
# answer_explained
# ====================================================================


class TestAnswerExplained:
    def test_returns_both_answer_and_scored_results(self, agent, emb_repo, llm):
        emb_repo.search.return_value = [
            _row(employee_no="EMP010", full_name="Alice", similarity=0.78),
            _row(employee_no="EMP011", full_name="Bob", similarity=0.61),
        ]
        llm.generate.return_value = "Found Alice and Bob."
        out = agent.answer_explained("python engineer", threshold=0.5)
        assert out["answer"] == "Found Alice and Bob."
        assert len(out["results"]) == 2
        for r in out["results"]:
            assert isinstance(r["explanation"], Explanation)

    def test_propagates_threshold(self, agent, emb_repo, llm):
        emb_repo.search.return_value = []
        llm.generate.return_value = "No results."
        agent.answer_explained("python", threshold=0.7)
        _args, _kwargs = emb_repo.search.call_args
        assert _kwargs["match_threshold"] == 0.7


# ====================================================================
# Backward-compat: existing search()/answer() APIs unchanged
# ====================================================================


class TestBackwardCompat:
    def test_search_still_returns_raw_rows(self, agent, emb_repo):
        rows = [_row()]
        emb_repo.search.return_value = rows
        assert agent.search("python") == rows

    def test_answer_still_returns_stripped_string(self, agent, emb_repo, llm):
        emb_repo.search.return_value = [_row()]
        llm.generate.return_value = "  some answer  "
        assert agent.answer("python") == "some answer"
