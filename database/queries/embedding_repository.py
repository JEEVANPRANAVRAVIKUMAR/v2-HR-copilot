"""
Embedding repository.

Stores and queries vector embeddings in Supabase via pgvector.
All vector operations go through the Supabase RPC mechanism.
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.constants import EMPLOYEE_EMBEDDINGS_TABLE
from database.queries.base_repository import BaseRepository
from utils.exceptions import RepositoryError


class EmbeddingRepository(BaseRepository):
    """
    Repository for storing and searching employee embeddings.
    """

    def store(
        self,
        employee_no: str,
        embedding: List[float],
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """
        Store or update an embedding for an employee.

        Args:
            employee_no: Employee identifier.
            embedding: Vector embedding.
            metadata: Optional metadata JSON.

        Raises:
            RepositoryError: If the operation fails.
        """
        try:
            data: Dict[str, Any] = {
                "employee_no": employee_no,
                "embedding": embedding,
            }
            if metadata:
                data["metadata"] = metadata

            response = self._execute(
                self.client
                .table(EMPLOYEE_EMBEDDINGS_TABLE)
                .upsert(data, on_conflict="employee_no")
            )
            if not self._has_data(response):
                raise RepositoryError("Embedding storage failed.")

            self.logger.info(
                "Embedding stored for %s.", employee_no,
            )

        except Exception as exc:
            self.logger.exception(
                "Failed storing embedding for %s.", employee_no,
            )
            raise RepositoryError(
                "Unable to store embedding."
            ) from exc

    def delete(self, employee_no: str) -> None:
        """
        Remove the embedding for an employee.

        Args:
            employee_no: Employee identifier.

        Raises:
            RepositoryError: If the operation fails.
        """
        try:
            self._execute(
                self.client
                .table(EMPLOYEE_EMBEDDINGS_TABLE)
                .delete()
                .eq("employee_no", employee_no)
            )
            self.logger.info(
                "Embedding deleted for %s.", employee_no,
            )

        except Exception as exc:
            self.logger.exception(
                "Failed deleting embedding for %s.", employee_no,
            )
            raise RepositoryError(
                "Unable to delete embedding."
            ) from exc

    def search(
        self,
        embedding: List[float],
        *,
        match_threshold: float = 0.5,
        match_count: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find employees by vector similarity.

        Args:
            embedding: Query vector.
            match_threshold: Minimum similarity (0-1).
            match_count: Maximum number of results.

        Returns:
            List of dicts with employee data and similarity scores.

        Raises:
            RepositoryError: If the search fails.
        """
        try:
            response = self._execute(
                self.client.rpc(
                    "match_employees",
                    {
                        "query_embedding": embedding,
                        "match_threshold": match_threshold,
                        "match_count": match_count,
                    },
                )
            )
            return response.data if self._has_data(response) else []

        except Exception as exc:
            self.logger.exception("Embedding search failed.")
            raise RepositoryError(
                "Unable to search embeddings."
            ) from exc
