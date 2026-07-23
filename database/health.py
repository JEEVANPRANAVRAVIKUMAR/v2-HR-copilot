"""
Database health checks.
"""

from __future__ import annotations

from core.constants import EMPLOYEES_TABLE
from database.client import DatabaseClient
from utils.logger import get_logger

logger = get_logger(__name__)


def check_database_connection() -> bool:
    """
    Verify that the database is reachable.

    A lightweight query is executed against the employee table.

    Returns:
        bool:
            True if the database is reachable,
            otherwise False.
    """

    try:

        client = DatabaseClient.get_client()

        client.table(EMPLOYEES_TABLE).select("id").limit(1).execute()

        logger.info("Database health check passed.")

        return True

    except Exception as exc:

        logger.exception(
            "Database health check failed."
        )

        return False