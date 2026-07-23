"""
Tests for EmbeddingGenerator.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ai import EmbeddingGenerator
from utils.exceptions import EmbeddingError


@pytest.fixture
def mock_model():
    """Return a fake SentenceTransformer model."""
    model = MagicMock()
    def encode(texts, **kwargs):
        if isinstance(texts, str):
            return np.array([0.1, 0.2, 0.3])
        return np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    model.encode.side_effect = encode
    model.get_sentence_embedding_dimension.return_value = 3
    return model


@pytest.fixture
def embedder(mock_model):
    with patch.object(
        EmbeddingGenerator, "_get_model", return_value=mock_model,
    ):
        yield EmbeddingGenerator(model_name="test-model")


class TestEmbed:
    def test_returns_float_list(self, embedder):
        vec = embedder.embed("Hello")
        assert isinstance(vec, list)
        assert all(isinstance(v, float) for v in vec)
        assert len(vec) == 3

    def test_batch_returns_list_of_lists(self, embedder):
        vecs = embedder.embed_batch(["A", "B"])
        assert len(vecs) == 2
        assert all(isinstance(v, list) for v in vecs)

    def test_embed_query_returns_vector(self, embedder):
        vec = embedder.embed_query("Find someone like this")
        assert isinstance(vec, list)
        assert len(vec) == 3


class TestEmbedErrors:
    def test_raises_on_model_failure(self, mock_model):
        mock_model.encode.side_effect = RuntimeError("OOM")
        with patch.object(
            EmbeddingGenerator, "_get_model", return_value=mock_model,
        ):
            gen = EmbeddingGenerator(model_name="test")
            with pytest.raises(EmbeddingError):
                gen.embed("text")

    def test_raises_on_batch_failure(self, mock_model):
        mock_model.encode.side_effect = RuntimeError("OOM")
        with patch.object(
            EmbeddingGenerator, "_get_model", return_value=mock_model,
        ):
            gen = EmbeddingGenerator(model_name="test")
            with pytest.raises(EmbeddingError):
                gen.embed_batch(["a", "b"])


class TestProperties:
    def test_model_name(self, embedder):
        assert embedder.model_name == "test-model"

    def test_dimension(self, embedder):
        assert embedder.dimension == 3
