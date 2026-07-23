"""
Dependency injection container for the HR AI Assistant.

This module provides a single place to store and access shared
application services initialized during bootstrap.
"""

from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from typing import TYPE_CHECKING, Any

from config import Settings

if TYPE_CHECKING:
    from ai import (
        GroqLLM, AIRouter, SqlAgent, ConversationMemory,
        EmbeddingGenerator, SemanticSearchAgent,
        CrudAgent, AnalyticsAgent,
    )
    from services import EmployeeService


@dataclass(slots=True)
class ServiceContainer:
    """
    Stores singleton instances shared across the application.
    """

    settings: Settings
    logger: Logger

    # Initialized during later phases
    supabase: Any | None = None
    llm: Any | None = None
    embedding_model: Any | None = None

    # Services
    employee_service: EmployeeService | None = None

    # AI layer
    groq_llm: GroqLLM | None = None
    ai_router: AIRouter | None = None
    sql_agent: SqlAgent | None = None
    conversation_memory: ConversationMemory | None = None
    embedding_generator: EmbeddingGenerator | None = None
    semantic_search_agent: SemanticSearchAgent | None = None
    crud_agent: CrudAgent | None = None
    analytics_agent: AnalyticsAgent | None = None


_container: ServiceContainer | None = None


def initialize_container(container: ServiceContainer) -> None:
    """
    Register the global application container.

    Args:
        container: Initialized service container.

    Raises:
        RuntimeError: If the container is already initialized.
    """
    global _container

    if _container is not None:
        raise RuntimeError("Service container is already initialized.")

    _container = container


def get_container() -> ServiceContainer:
    """
    Return the initialized service container.

    Raises:
        RuntimeError: If bootstrap has not been executed.
    """
    if _container is None:
        raise RuntimeError(
            "Application has not been bootstrapped."
        )

    return _container