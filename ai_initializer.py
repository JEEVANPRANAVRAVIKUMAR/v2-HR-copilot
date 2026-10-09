"""
Dedicated AI Session Initializer for HR Chatbot Streamlit app.
"""

from __future__ import annotations
import logging
import streamlit as st

INIT_VERSION = "2.1.5"

def initialize_ai_session(force: bool = False) -> bool:
    """Lazy-initialize AI components into st.session_state."""
    if not force and st.session_state.get("chat_initialized", False) and st.session_state.get("init_version") == INIT_VERSION:
        return True
    try:
        from config import get_settings
        get_settings.cache_clear()
        from ai import (
            GroqLLM, ConversationMemory, AIRouter, Planner, is_complex,
            SqlAgent, CrudAgent, SemanticSearchAgent, AnalyticsAgent,
            EmbeddingGenerator, HistoryAgent,
        )
        from database.queries import (
            EmployeeRepository, SqlQueryRepository,
            EmbeddingRepository, AnalyticsRepository,
            EmployeeHistoryRepository,
        )
        from database.client import DatabaseClient
        from services import EmployeeService, EmployeeHistoryService
        from services.workforce_agents import (
            RecommendationEngine, TeamBuilder, PromotionAnalyzer,
            TransferAnalyzer, AttritionRisk, SkillGapAgent, InsightAgent,
        )
        from utils.logger import get_logger

        settings = get_settings()
        logger = get_logger("assistant")

        # Force client initialization so repositories can be built.
        DatabaseClient.get_client()

        llm = GroqLLM(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            logger=logger,
        )

        # Repositories
        emp_repo = EmployeeRepository()
        history_repo = EmployeeHistoryRepository()
        sql_repo = SqlQueryRepository()
        embed_repo = EmbeddingRepository()
        analytics_repo = AnalyticsRepository()

        # Services
        history_service = EmployeeHistoryService(history_repo, logger)
        employee_service = EmployeeService(
            repository=emp_repo, logger=logger, history_service=history_service,
        )

        # Embedder for semantic search.
        embedder = EmbeddingGenerator(
            model_name=settings.embedding_model, logger=logger,
        )

        # Core agents.
        st.session_state.llm = llm
        st.session_state.memory = ConversationMemory()
        st.session_state.router = AIRouter(llm, logger)
        st.session_state.sql_agent = SqlAgent(llm, sql_repo, logger)
        st.session_state.crud_agent = CrudAgent(llm, employee_service, logger)
        st.session_state.semantic_agent = SemanticSearchAgent(
            embedder, embed_repo, llm, logger,
        )
        st.session_state.analytics_agent = AnalyticsAgent(
            analytics_repo, llm, logger,
        )
        st.session_state.history_agent = HistoryAgent(
            llm, history_service, employee_service, logger,
        )

        # Workforce agents.
        st.session_state.recommendation_engine = RecommendationEngine(
            employee_service, history_service, logger,
        )
        st.session_state.team_builder = TeamBuilder(
            st.session_state.recommendation_engine, logger,
        )
        st.session_state.promotion_analyzer = PromotionAnalyzer(
            history_service, employee_service, logger,
        )
        st.session_state.transfer_analyzer = TransferAnalyzer(
            employee_service, history_service,
            st.session_state.analytics_agent, logger,
        )
        st.session_state.attrition_risk = AttritionRisk(
            history_service, employee_service,
            st.session_state.analytics_agent, logger,
        )
        st.session_state.skill_gap_agent = SkillGapAgent(
            employee_service, st.session_state.analytics_agent, logger,
        )
        st.session_state.insight_agent = InsightAgent(
            st.session_state.analytics_agent, logger,
        )

        # Planner.
        st.session_state.planner = Planner(llm, logger)
        st.session_state.is_complex = is_complex

        st.session_state.chat_initialized = True
        st.session_state.init_version = INIT_VERSION
        return True

    except Exception as exc:
        logging.getLogger("assistant").exception("AI initialization failed")
        st.session_state.init_error = str(exc)
        return False
