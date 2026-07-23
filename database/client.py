"""
Database client management.

This module owns the application's database connection.
No other module should create a Supabase client directly.
"""

from __future__ import annotations

from threading import Lock

from supabase import Client, create_client

from config import get_settings
from utils.exceptions import DatabaseConnectionError
from utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseClient:
    """
    Thread-safe singleton wrapper around the Supabase client.
    """

    _client: Client | None = None
    _lock = Lock()

    @classmethod
    def get_client(cls) -> Client:
        """
        Return the shared Supabase client.

        The client is lazily initialized and reused throughout
        the application's lifetime.

        Returns:
            Client: Shared Supabase client.

        Raises:
            DatabaseConnectionError:
                If the client cannot be initialized.
        """

        if cls._client is None:

            with cls._lock:

                if cls._client is None:

                    settings = get_settings()

                    try:

                        cls._client = create_client(
                            settings.supabase_url,
                            settings.supabase_key,
                        )

                        logger.info(
                            "Supabase client initialized successfully."
                        )

                    except Exception as exc:

                        logger.exception(
                            "Unable to initialize Supabase client."
                        )

                        raise DatabaseConnectionError(
                            "Failed to initialize Supabase client."
                        ) from exc

        return cls._client

    @classmethod
    def reset(cls) -> None:
        """
        Reset the shared client.

        Primarily intended for unit testing.
        """

        with cls._lock:
            cls._client = None

        logger.info("Supabase client has been reset.")