"""
Tests for SemanticSearchAgent.
"""

from __future__ import annotations

from logging import Logger
from unittest.mock import MagicMock, create_autospec

import pytest

from ai import EmbeddingGenerator, GroqLLM, SemanticSearchAgent
from database.queries import EmbeddingRepository
from utils.exceptions import EmbeddingError, ServiceError


@pytest.fixture
def embedder():
    mock = create_autospec(EmbeddingGenerator, instance=True)
    mock.embed_query.return_value = [0.1, 0.2, 0.3]
    return mock


@pytest.fixture
def embedding_repo():
    return create_autospec(EmbeddingRepository, instance=True)


@pytest.fixture
def llm():
    return create_autospec(GroqLLM, instance=True)


@pytest.fixture
def logger():
    return create_autospec(Logger, instance=True)


@pytest.fixture
def agent(embedder, embedding_repo, llm, logger):
    return SemanticSearchAgent(
        embedder=embedder,
        embedding_repo=embedding_repo,
        llm=llm,
        logger=logger,
    )


class TestSearch:
    def test_returns_results(self, agent, embedding_repo):
        embedding_repo.search.return_value = [
            {"employee_no": "EMP001", "full_name": "John", "similarity": 0.95},
        ]
        results = agent.search("python developer")
        assert len(results) == 1
        assert results[0]["employee_no"] == "EMP001"

    def test_returns_empty_when_no_matches(self, agent, embedding_repo):
        embedding_repo.search.return_value = []
        assert agent.search("nothing") == []

    def test_wraps_embedding_error(self, agent, embedder):
        embedder.embed_query.side_effect = EmbeddingError("fail")
        with pytest.raises(ServiceError, match="Embedding generation failed"):
            agent.search("test")


class TestAnswer:
    def test_returns_nl_answer(self, agent, embedding_repo, llm):
        embedding_repo.search.return_value = [
            {"employee_no": "EMP001", "full_name": "John", "similarity": 0.95},
        ]
        llm.generate.return_value = "John is the best match."
        answer = agent.answer("python developer")
        assert "John" in answer

    def test_handles_no_results(self, agent, embedding_repo, llm):
        embedding_repo.search.return_value = []
        llm.generate.return_value = "No matches found."
        answer = agent.answer("nothing")
        assert "No matches" in answer
