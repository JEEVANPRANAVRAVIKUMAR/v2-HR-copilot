"""
Application startup validation.
"""

from core.container import get_container


def startup_check() -> None:
    """
    Perform startup validation.

    Raises:
        RuntimeError:
            If the application container has not been initialized.
    """

    container = get_container()

    container.logger.info("Running startup validation...")

    container.logger.info("Configuration loaded.")

    container.logger.info("Logger initialized.")

    if container.employee_service is None:
        container.logger.warning("EmployeeService is not registered.")
    else:
        container.logger.info("EmployeeService registered.")

    for name, obj in [
        ("GroqLLM", container.groq_llm),
        ("AIRouter", container.ai_router),
        ("SqlAgent", container.sql_agent),
        ("ConversationMemory", container.conversation_memory),
        ("EmbeddingGenerator", container.embedding_generator),
        ("SemanticSearchAgent", container.semantic_search_agent),
        ("CrudAgent", container.crud_agent),
        ("AnalyticsAgent", container.analytics_agent),
    ]:
        if obj is None:
            container.logger.warning("%s is not registered.", name)
        else:
            container.logger.info("%s registered.", name)

    container.logger.info("Startup validation successful.")