"""
Embedding generation using Sentence Transformers.

Wraps the sentence-transformers library so no other module needs
to import it directly. The model is loaded once and cached.
"""

from __future__ import annotations

import logging
from logging import Logger
from typing import List

from utils.exceptions import EmbeddingError


class EmbeddingGenerator:
    """
    Generates vector embeddings from text using Sentence Transformers.

    The underlying model is loaded lazily on first use and cached
    for the lifetime of the application.
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        logger: Logger | None = None,
    ) -> None:
        self._model_name = model_name
        self._model = None
        self._logger = logger or logging.getLogger(__name__)

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def embed(self, text: str) -> List[float]:
        """
        Generate an embedding vector for a single text string.

        Args:
            text: Input text.

        Returns:
            Dense vector as a list of floats.

        Raises:
            EmbeddingError: If embedding generation fails.
        """
        try:
            model = self._get_model()
            vector = model.encode(text, show_progress_bar=False)
            return vector.tolist()

        except Exception as exc:
            self._logger.exception("Embedding generation failed.")
            raise EmbeddingError(
                "Failed to generate embedding."
            ) from exc

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in one batch.

        Args:
            texts: List of input texts.

        Returns:
            List of dense vectors.

        Raises:
            EmbeddingError: If embedding generation fails.
        """
        try:
            model = self._get_model()
            vectors = model.encode(texts, show_progress_bar=False)
            return [v.tolist() for v in vectors]

        except Exception as exc:
            self._logger.exception(
                "Batch embedding generation failed."
            )
            raise EmbeddingError(
                "Failed to generate batch embeddings."
            ) from exc

    def embed_query(self, query: str) -> List[float]:
        """
        Generate a query embedding optimised for retrieval.

        For sentence-transformers models this is identical to
        ``embed()``, but the method exists so we can apply
        query-specific prefixes if the model supports them.

        Args:
            query: Search query text.

        Returns:
            Query vector.
        """
        return self.embed(query)

    @property
    def model_name(self) -> str:
        """The configured Sentence Transformers model name."""
        return self._model_name

    @property
    def dimension(self) -> int:
        """
        Embedding dimension. Loads the model to determine this.

        Raises:
            EmbeddingError: If the model cannot be loaded.
        """
        try:
            model = self._get_model()
            return model.get_sentence_embedding_dimension()

        except Exception as exc:
            raise EmbeddingError(
                "Unable to determine embedding dimension."
            ) from exc

    # ----------------------------------------------------------------
    # Internal
    # ----------------------------------------------------------------

    def _get_model(self):
        """Lazy-load the sentence-transformers model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._logger.info(
                "Loading embedding model: %s", self._model_name,
            )
            self._model = SentenceTransformer(self._model_name)
            self._logger.info("Embedding model loaded.")

        return self._model
