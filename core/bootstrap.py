"""
Application bootstrap.

Responsible for initializing shared services.
"""

from config import get_settings
from core.container import (
    ServiceContainer,
    initialize_container,
)
from utils.logger import get_logger


def bootstrap() -> None:
    """
    Initialize the application.

    This function should be called exactly once before
    launching the UI.
    """

    settings = get_settings()

    logger = get_logger(__name__)

    container = ServiceContainer(
        settings=settings,
        logger=logger,
    )

    # ----------------------------------------------------------------
    # Repositories
    # ----------------------------------------------------------------
    from database.queries import (
        AnalyticsRepository,
        EmbeddingRepository,
        EmployeeRepository,
        SqlQueryRepository,
    )

    employee_repo = EmployeeRepository()
    sql_query_repo = SqlQueryRepository()
    embedding_repo = EmbeddingRepository()
    analytics_repo = AnalyticsRepository()

    # ----------------------------------------------------------------
    # AI layer
    # ----------------------------------------------------------------
    from ai import (
        GroqLLM, AIRouter, SqlAgent, ConversationMemory,
        EmbeddingGenerator, SemanticSearchAgent,
        CrudAgent, AnalyticsAgent,
    )

    groq_llm = GroqLLM(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        logger=logger,
    )
    container.groq_llm = groq_llm

    container.ai_router = AIRouter(llm=groq_llm, logger=logger)

    container.sql_agent = SqlAgent(
        llm=groq_llm,
        sql_repo=sql_query_repo,
        logger=logger,
    )

    container.conversation_memory = ConversationMemory()

    # Embedding generator & semantic search
    embedding_gen = EmbeddingGenerator(
        model_name=settings.embedding_model,
        logger=logger,
    )
    container.embedding_generator = embedding_gen

    container.semantic_search_agent = SemanticSearchAgent(
        embedder=embedding_gen,
        embedding_repo=embedding_repo,
        llm=groq_llm,
        logger=logger,
    )

    # ----------------------------------------------------------------
    # Services
    # ----------------------------------------------------------------
    from services import EmployeeService

    container.employee_service = EmployeeService(
        repository=employee_repo,
        logger=logger,
    )

    # CRUD & Analytics agents depend on services
    container.crud_agent = CrudAgent(
        llm=groq_llm,
        employee_service=container.employee_service,
        logger=logger,
    )

    container.analytics_agent = AnalyticsAgent(
        analytics_repo=analytics_repo,
        llm=groq_llm,
        logger=logger,
    )

    initialize_container(container)

    logger.info("Bootstrap completed successfully.")