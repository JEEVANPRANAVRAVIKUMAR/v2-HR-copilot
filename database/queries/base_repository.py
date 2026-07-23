"""
Base repository.

Provides shared functionality for all repositories.
"""

from __future__ import annotations

from typing import Any

from database.client import DatabaseClient
from utils.exceptions import RepositoryError
from utils.logger import get_logger


class BaseRepository:
    """
    Base class for all repositories.

    Responsibilities:
        - Provide access to the shared database client.
        - Provide repository-level logging.
        - Provide common exception handling helpers.
    """

    def __init__(self) -> None:
        self._client = DatabaseClient.get_client()
        self._logger = get_logger(self.__class__.__name__)

    @property
    def client(self):
        """
        Return the shared Supabase client.
        """
        return self._client

    @property
    def logger(self):
        """
        Return the repository logger.
        """
        return self._logger

    def _execute(self, query: Any):
        """
        Execute a Supabase query with centralized error handling.

        Args:
            query:
                A prepared Supabase query.

        Returns:
            The Supabase response.

        Raises:
            RepositoryError:
                If query execution fails.
        """

        try:

            response = query.execute()

            return response

        except Exception as exc:

            self.logger.exception(
                "Repository query execution failed."
            )

            raise RepositoryError(
                "Database operation failed."
            ) from exc

    @staticmethod
    def _has_data(response: Any) -> bool:
        """
        Check whether a Supabase response contains data.

        Args:
            response:
                Supabase response.

        Returns:
            bool:
                True if response contains data.
        """

        return (
            response is not None
            and hasattr(response, "data")
            and response.data is not None
            and len(response.data) > 0
        )